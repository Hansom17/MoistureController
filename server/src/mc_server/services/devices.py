"""Devices, keys, pairing bundles and config sync (Server_Specs §8)."""

from sqlalchemy import select

from mc_core import ids, pins
from mc_core.commands import Actuator
from mc_core.contract import topics
from mc_core.contract.device import ConfigDesired, Limits, SlotConfig

from ..context import Uow
from ..db.models import CommandRow, ConfigRevision, Device, Plant
from ..db.types import utcnow
from ..errors import Problem
from . import hubs
from .common import audit, get_hub

DEFAULT_WAKE_S = 600
BATTERY_EMPTY_MV, BATTERY_FULL_MV = 3300, 4150


# --- views ---------------------------------------------------------------------


def sync_state(d: Device) -> str:
    if d.desired_rev == d.reported_rev:
        return "in_sync"
    if d.rejected_rev is not None and d.rejected_rev == d.desired_rev:
        return "rejected"
    return "pending"


def battery_percent(mv: int | None) -> int | None:
    if mv is None:
        return None
    pct = (mv - BATTERY_EMPTY_MV) * 100 / (BATTERY_FULL_MV - BATTERY_EMPTY_MV)
    return int(max(0, min(100, round(pct))))


def reported_limits(d: Device) -> Limits:
    raw = (d.reported_config or {}).get("limits")
    return Limits.model_validate(raw) if raw else pins.DEFAULT_LIMITS


def reported_slots(d: Device) -> list[SlotConfig]:
    return [SlotConfig.model_validate(s) for s in (d.reported_config or {}).get("slots", [])]


def actuator(d: Device, slot: int) -> Actuator | None:
    """Pump slot from the **reported** config (§7.1); None if not an actuator."""
    for s in reported_slots(d):
        if s.slot == slot and s.is_actuator:
            return Actuator(slot=s.slot, max_run_s=s.max_run_s or 0,
                            min_pause_s=s.min_pause_s or 0,
                            hard_limit_s=reported_limits(d).max_run_s_hard)
    return None


# --- adding, re-keying, removing ------------------------------------------------


async def _gateway_for(uow: Uow, household_id: str) -> tuple[str, str, int]:
    """(gateway, host, port) for a new pairing bundle (§8.1 step 2)."""
    hub = await get_hub(uow, household_id)
    if hub is None:
        s = uow.ctx.settings
        return "cloud", s.broker_public_host, s.broker_public_port
    if not hub.bridge_connected:
        raise Problem(409, "hub_offline")
    state = hub.last_state or {}
    host = hub.lan_host_override or state.get("lan_host")
    if not host:
        raise Problem(409, "hub_offline", "hub has not reported its LAN address yet")
    return "hub", host, int(state.get("lan_port", 8883))


async def _install_key(uow: Uow, device: Device) -> dict:
    gateway, host, port = await _gateway_for(uow, device.household_id)
    psk = ids.new_psk()
    device.psk_enc = uow.ctx.keys.encrypt(psk)
    device.gateway = gateway
    uow.broker_files_changed()  # cloud PSK file, or the hub's ACL on the cloud broker
    if gateway == "hub":
        await hubs.publish_keys(uow, device.household_id)
    return {"device_id": device.id, "mqtt": {"host": host, "port": port, "psk": psk}}


async def create_device(uow: Uow, household_id: str, name: str, uid: str) -> tuple[Device, dict]:
    device = Device(id=ids.new_device_id(), household_id=household_id, name=name,
                    status="new", wake_interval_s=DEFAULT_WAKE_S)
    uow.s.add(device)
    await uow.s.flush()
    bundle = await _install_key(uow, device)
    await _set_desired(uow, device, ConfigDesired(rev=1, wake_interval_s=DEFAULT_WAKE_S), uid)
    audit(uow, household_id, uid, "device.create", {"device_id": device.id, "name": name})
    uow.emit(household_id, "device", {"id": device.id})
    await uow.commit()
    return device, bundle


async def rekey(uow: Uow, device: Device, uid: str) -> dict:
    bundle = await _install_key(uow, device)
    audit(uow, device.household_id, uid, "device.rekey", {"device_id": device.id})
    uow.emit(device.household_id, "device", {"id": device.id})
    await uow.commit()
    return bundle


async def delete_device(uow: Uow, device: Device, uid: str) -> None:
    """Keeps history; removes key, retained topics and open commands (§8.1)."""
    hid = device.household_id
    device.deleted_at = utcnow()
    device.psk_enc = None
    device.gateway = "none"
    for suffix in ("status", "config/desired", "config/state"):
        uow.publish(topics.device(device.id, suffix), None, retain=True)
    open_cmds = await uow.s.scalars(select(CommandRow).where(
        CommandRow.device_id == device.id,
        CommandRow.status.in_(("queued", "delivered", "cancelling"))))
    for c in open_cmds:
        c.status, c.reason, c.finished_at = "cancelled", "device_removed", utcnow()
    for p in await uow.s.scalars(select(Plant).where(Plant.household_id == hid)):
        if p.sensor_device_id == device.id:
            p.sensor_device_id, p.sensor_slot = None, None
        if p.pump_device_id == device.id:
            p.pump_device_id, p.pump_slot = None, None
    uow.broker_files_changed()
    if await get_hub(uow, hid) is not None:
        await hubs.publish_keys(uow, hid)
    await hubs.republish_snapshot(uow, hid)
    audit(uow, hid, uid, "device.delete", {"device_id": device.id})
    uow.emit(hid, "device", {"id": device.id, "deleted": True})
    await uow.commit()


# --- config sync (§8.2) ----------------------------------------------------------


async def _set_desired(uow: Uow, device: Device, cfg: ConfigDesired, uid: str | None) -> None:
    body = cfg.model_dump(exclude_none=True)
    device.desired_rev = cfg.rev
    device.desired_config = body
    uow.s.add(ConfigRevision(device_id=device.id, rev=cfg.rev, kind="desired", body=body,
                             created_by=uid))
    uow.publish(topics.device(device.id, "config/desired"), body, retain=True)


async def put_config(uow: Uow, device: Device, base_rev: int, wake_interval_s: int,
                     slots: list[dict], uid: str) -> Device:
    if base_rev != device.desired_rev:
        raise Problem(409, "config_rev_conflict", current_rev=device.desired_rev)
    try:
        cfg = ConfigDesired(rev=device.desired_rev + 1, wake_interval_s=wake_interval_s,
                            slots=slots)
    except ValueError as e:
        raise Problem(422, "out_of_range", str(e)) from e
    errors = pins.validate_config(cfg, reported_limits(device))
    if errors:
        raise Problem(422, errors[0].code, errors[0].detail,
                      errors=[e.model_dump(exclude_none=True) for e in errors])
    # The hub snapshot is rebuilt when the device *reports* the new config
    # (ingest), since command checks use the reported limits.
    await _set_desired(uow, device, cfg, uid)
    uow.emit(device.household_id, "config", {"device_id": device.id, "rev": cfg.rev})
    await uow.commit()
    return device


def actuator_limits(body: dict | None) -> list:
    """What the hub snapshot needs from a config; used to detect changes."""
    body = body or {}
    return [body.get("wake_interval_s"), body.get("limits")] + [
        (s.get("slot"), s.get("max_run_s"), s.get("min_pause_s"))
        for s in body.get("slots", []) if s.get("module") == "pump_relay"]


def config_view(d: Device) -> dict:
    return {
        "device_id": d.id,
        "desired": d.desired_config,
        "desired_rev": d.desired_rev,
        "reported": d.reported_config,
        "reported_rev": d.reported_rev,
        "sync_state": sync_state(d),
        "rejected_rev": d.rejected_rev,
        "error": d.config_error,
        "detected": (d.reported_config or {}).get("detected", []),
        "limits": reported_limits(d).model_dump(),
        "board": d.board,
    }


def view(d: Device) -> dict:
    return {
        "id": d.id, "name": d.name, "board": d.board, "status": d.status, "gateway": d.gateway,
        "fw": d.fw, "batt_mv": d.batt_mv, "battery_percent": battery_percent(d.batt_mv),
        "rssi": d.rssi, "last_seen_at": d.last_seen_at, "next_expected_at": d.next_expected_at,
        "wake_interval_s": d.wake_interval_s, "sync_state": sync_state(d),
        "desired_rev": d.desired_rev, "reported_rev": d.reported_rev,
        "config_error": d.config_error, "created_at": d.created_at,
    }
