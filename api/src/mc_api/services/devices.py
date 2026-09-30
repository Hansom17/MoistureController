"""Devices, keys, pairing bundles and config sync (Api_Specs §8)."""

from sqlalchemy import select

from mc_core import ids, pins
from mc_core.commands import Actuator
from mc_core.contract.device import ConfigDesired, Limits, SlotConfig

from ..context import Uow
from ..db.models import CommandRow, ConfigRevision, Device, Plant
from ..db.types import utcnow
from ..errors import Problem
from . import gateways
from .common import audit

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


async def _install_key(uow: Uow, device: Device, require_online: bool = True) -> dict:
    """New PSK, sent to the household's gateway in its key set; returns the
    pairing bundle with the gateway's LAN address (Api_Specs §8.1).

    The gateway applies keys within seconds; BLE pairing takes longer, so the
    bundle is returned without waiting for its `down_ack`.
    """
    gw = await gateways.get_gateway(uow, device.household_id)
    if gw is None:
        raise Problem(409, "no_gateway", "add a gateway to this household first")
    if require_online and not gateways.is_online(uow, gw):
        raise Problem(409, "gateway_offline")
    host, port = gateways.lan_address(gw)
    if not host and require_online:
        raise Problem(409, "gateway_offline", "the gateway has not reported its LAN address")
    if device.adapter not in (gw.adapters or ["esp32-mqtt"]):
        raise Problem(422, "adapter_unsupported", device.adapter)
    psk = ids.new_psk()
    device.psk_enc = uow.ctx.keys.encrypt(psk)
    device.gateway = "gateway"
    await uow.s.flush()
    await gateways.publish_keys(uow, device.household_id)
    await gateways.republish_snapshot(uow, device.household_id)  # device joins the snapshot
    return {"device_id": device.id, "mqtt": {"host": host, "port": port, "psk": psk}}


async def create_device(uow: Uow, household_id: str, name: str, uid: str,
                        adapter: str = "esp32-mqtt",
                        require_online: bool = True) -> tuple[Device, dict]:
    device = Device(id=ids.new_device_id(), household_id=household_id, name=name,
                    adapter=adapter, status="new", wake_interval_s=DEFAULT_WAKE_S)
    uow.s.add(device)
    await uow.s.flush()
    bundle = await _install_key(uow, device, require_online)
    await _set_desired(uow, device, ConfigDesired(rev=1, wake_interval_s=DEFAULT_WAKE_S), uid)
    audit(uow, household_id, uid, "device.create", {"device_id": device.id, "name": name})
    uow.emit(household_id, "device", {"id": device.id})
    await uow.commit()
    return device, bundle


async def rekey(uow: Uow, device: Device, uid: str, require_online: bool = True) -> dict:
    bundle = await _install_key(uow, device, require_online)
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
    await gateways.send_down(uow, hid, "device_removed", {"device": device.id})
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
    await uow.s.flush()
    await gateways.publish_keys(uow, hid)
    await gateways.republish_snapshot(uow, hid)
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
    await gateways.send_down(uow, device.household_id, "config_desired",
                             {"device": device.id, "config": body})


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
    await _set_desired(uow, device, cfg, uid)
    uow.emit(device.household_id, "config", {"device_id": device.id, "rev": cfg.rev})
    await uow.commit()
    return device


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
        "id": d.id, "name": d.name, "board": d.board, "status": d.status, "adapter": d.adapter,
        "needs_repair": d.gateway == "none",
        "fw": d.fw, "batt_mv": d.batt_mv, "battery_percent": battery_percent(d.batt_mv),
        "rssi": d.rssi, "last_seen_at": d.last_seen_at, "next_expected_at": d.next_expected_at,
        "wake_interval_s": d.wake_interval_s, "sync_state": sync_state(d),
        "desired_rev": d.desired_rev, "reported_rev": d.reported_rev,
        "config_error": d.config_error, "created_at": d.created_at,
    }
