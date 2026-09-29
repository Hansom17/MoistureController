"""Ingest of normalized device messages from gateways (Api_Specs §9.5).

The payloads are the mqtt.md shapes (the canonical device model).
"""

import json
import logging
import time
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select

from mc_core.contract.device import (
    MAX_DEVICE_TO_SERVER,
    CmdAck,
    ConfigState,
    Event,
    Status,
    Telemetry,
)
from mc_core.contract.gateway import DeviceMessage

from ..context import Uow
from ..db.models import (
    ConfigRevision,
    Device,
    DeviceEvent,
    HealthReport,
    Household,
    Plant,
    ReadingRow,
)
from ..db.types import utcnow
from . import alerts, commands
from .common import to_dt

log = logging.getLogger(__name__)

TS_PAST = timedelta(hours=2)
TS_FUTURE = timedelta(minutes=5)
SENSOR_ERROR_CYCLES = 3
_unknown_logged: dict[str, float] = {}


PARSERS = {"status": Status, "telemetry": Telemetry, "event": Event, "cmd_ack": CmdAck,
           "config_state": ConfigState}


async def handle_device(uow: Uow, household_id: str, msg: DeviceMessage,
                        outage_s: int = 0, commit: bool = True) -> None:
    """One normalized device message from the household's gateway (Api_Specs §9.5).

    Messages for devices of other households are dropped. With `commit=False`
    the caller commits (together with the gateway's `last_up_seq`).
    """
    device = await uow.s.get(Device, msg.device)
    if device is None or device.deleted_at is not None or device.household_id != household_id:
        if time.monotonic() - _unknown_logged.get(msg.device, 0) > 300:
            _unknown_logged[msg.device] = time.monotonic()
            log.info("message for unknown or foreign device %s", msg.device)
        return
    device_id = device.id  # stays valid after a rollback
    received = to_dt(msg.received_at)
    if len(json.dumps(msg.payload)) > MAX_DEVICE_TO_SERVER:
        _invalid(uow, device_id, f"{msg.kind}: payload too large")
        if commit:
            await uow.commit()
        return
    try:
        body = PARSERS[msg.kind].model_validate(msg.payload)
        match msg.kind:
            case "status":
                await _status(uow, device, body, received)
            case "telemetry":
                await _telemetry(uow, device, body, received, outage_s)
            case "event":
                await _event(uow, device, body, received, outage_s)
            case "cmd_ack":
                await commands.handle_ack(uow, device, body)
            case "config_state":
                await _config_state(uow, device, body)
    except (ValueError, ValidationError) as e:
        await uow.rollback()
        _invalid(uow, device_id, f"{msg.kind}: {str(e)[:200]}")
    if commit:
        await uow.commit()


def _invalid(uow: Uow, device_id: str, detail: str) -> None:
    uow.s.add(DeviceEvent(device_id=device_id, ts=utcnow(), kind="invalid_payload",
                          detail=detail))


# --- status (§8.3) -------------------------------------------------------------------


async def _status(uow: Uow, device: Device, msg: Status, received) -> None:
    now = received  # replayed messages count from when the gateway got them
    hid = device.household_id
    if msg.boot is not None:
        if device.last_boot is not None and msg.boot < device.last_boot:
            device.last_seq = None  # power loss: seq restarted too (§10.2)
        device.last_boot = msg.boot
    if msg.fw:
        device.fw = msg.fw
    device.status = msg.state
    if msg.state == "offline":
        await alerts.open_alert(uow, hid, "device_crashed", "device", device.id, device.name)
    else:
        device.last_seen_at = now
        wait = msg.next_wake_s if msg.state == "sleeping" and msg.next_wake_s else (
            msg.until_s if msg.state == "service" and msg.until_s else device.wake_interval_s)
        device.next_expected_at = now + timedelta(seconds=wait)
        if msg.state == "online":
            await alerts.resolve_alert(uow, hid, "device_offline", device.id)
            await alerts.resolve_alert(uow, hid, "device_crashed", device.id)
    uow.emit(hid, "device", {"id": device.id, "status": device.status})


# --- telemetry ------------------------------------------------------------------------


async def _accept_seq(device: Device, seq: int) -> bool:
    if device.last_seq is not None and seq <= device.last_seq:
        return False
    device.last_seq = seq
    return True


def _timestamp(ts: int | None, received, outage_s: int):
    """Device time if plausible: [received − 2 h − gateway outage, received + 5 min]."""
    if ts is None:
        return received, "gateway"
    at = to_dt(ts)
    if received - TS_PAST - timedelta(seconds=outage_s) <= at <= received + TS_FUTURE:
        return at, "device"
    return received, "gateway"


async def _telemetry(uow: Uow, device: Device, msg: Telemetry, received,
                     outage_s: int) -> None:
    if not await _accept_seq(device, msg.seq):
        return  # duplicate after reconnect
    hid = device.household_id
    household = await uow.s.get(Household, hid)
    at, source = _timestamp(msg.ts, received, outage_s)
    plants = {(p.sensor_slot): p for p in await uow.s.scalars(select(Plant).where(
        Plant.household_id == hid, Plant.sensor_device_id == device.id,
        Plant.archived_at.is_(None)))}
    streak = dict(device.sensor_error_streak or {})
    touched: list[str] = []

    for r in msg.readings:
        plant = plants.get(r.slot)
        uow.s.add(ReadingRow(device_id=device.id, slot=r.slot,
                             plant_id=plant.id if plant else None, type=r.type, value=r.value,
                             raw=r.raw, error=r.error, ts=at, ts_source=source, seq=msg.seq))
        key = str(r.slot)
        if r.error:
            streak[key] = streak.get(key, 0) + 1
            if streak[key] == SENSOR_ERROR_CYCLES:
                await alerts.open_alert(uow, hid, "sensor_error", "device", device.id,
                                        plant.name if plant else device.name,
                                        {"slot": r.slot, "error": r.error})
        elif key in streak:
            streak.pop(key)
            if not any(v >= SENSOR_ERROR_CYCLES for v in streak.values()):
                await alerts.resolve_alert(uow, hid, "sensor_error", device.id)
        if plant is not None and r.type == "soil_moisture":
            touched.append(plant.id)  # rules run on the gateway (D36)
    device.sensor_error_streak = streak

    h = msg.health
    uow.s.add(HealthReport(device_id=device.id, ts=at, seq=msg.seq, batt_mv=h.batt_mv,
                           rssi=h.rssi, wake=h.wake, cycle_ms=h.cycle_ms, wifi_ms=h.wifi_ms))
    device.batt_mv, device.rssi = h.batt_mv, h.rssi
    device.last_seen_at = received
    await _battery(uow, device, household)
    uow.emit(hid, "reading", {"device_id": device.id, "plant_ids": touched})


async def _battery(uow: Uow, device: Device, household: Household) -> None:
    """`battery_low` after 3 reports below the threshold; resolved +100 mV above."""
    threshold = household.battery_low_mv
    await uow.s.flush()
    last = (await uow.s.scalars(select(HealthReport.batt_mv).where(
        HealthReport.device_id == device.id).order_by(HealthReport.id.desc()).limit(3))).all()
    if len(last) == 3 and all(mv < threshold for mv in last):
        await alerts.open_alert(uow, household.id, "battery_low", "device", device.id,
                                device.name, {"batt_mv": last[0]})
    elif last and last[0] > threshold + 100:
        await alerts.resolve_alert(uow, household.id, "battery_low", device.id)


# --- events ----------------------------------------------------------------------------


async def _event(uow: Uow, device: Device, msg: Event, received, outage_s: int) -> None:
    if not await _accept_seq(device, msg.seq):
        return
    at, _ = _timestamp(msg.ts, received, outage_s)
    hid = device.household_id
    uow.s.add(DeviceEvent(device_id=device.id, ts=at, seq=msg.seq, kind=msg.kind,
                          slot=msg.slot, detail=msg.detail))
    if msg.kind == "safety_stop":
        await alerts.open_alert(uow, hid, "safety_stop", "device", device.id, device.name,
                                {"slot": msg.slot, "detail": msg.detail})
    elif msg.kind == "low_battery":
        await alerts.open_alert(uow, hid, "battery_low", "device", device.id, device.name)
    uow.emit(hid, "device", {"id": device.id, "event": msg.kind})


# --- config/state (§8.2) -------------------------------------------------------------------


async def _config_state(uow: Uow, device: Device, msg: ConfigState) -> None:
    hid = device.household_id
    body = msg.model_dump(exclude_none=True)
    before = _snapshot_relevant(device.reported_config)
    device.reported_rev = msg.rev
    device.reported_config = body
    device.wake_interval_s = msg.wake_interval_s
    uow.s.add(ConfigRevision(device_id=device.id, rev=msg.rev, kind="reported", body=body,
                             result=msg.result,
                             error=msg.error.model_dump() if msg.error else None))
    if msg.result == "rejected":
        device.rejected_rev = msg.rejected_rev
        device.config_error = msg.error.model_dump(exclude_none=True) if msg.error else None
        if msg.rejected_rev == device.desired_rev:
            await alerts.open_alert(uow, hid, "config_rejected", "device", device.id,
                                    device.name, device.config_error)
    elif device.reported_rev == device.desired_rev:
        device.rejected_rev, device.config_error = None, None
        await alerts.resolve_alert(uow, hid, "config_rejected", device.id)
    if _snapshot_relevant(body) != before:
        # Pump limits and wake interval are part of the gateway's snapshot.
        from . import gateways

        await gateways.republish_snapshot(uow, hid)
    uow.emit(hid, "config", {"device_id": device.id, "rev": msg.rev})


def _snapshot_relevant(body: dict | None) -> list:
    body = body or {}
    return [body.get("wake_interval_s"), body.get("limits")] + [
        (s.get("slot"), s.get("max_run_s"), s.get("min_pause_s"))
        for s in body.get("slots", []) if s.get("module") == "pump_relay"]
