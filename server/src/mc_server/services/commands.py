"""Command service: creation, cancel, acks, expiry (Api_Specs §7)."""

import logging
from datetime import timedelta

from sqlalchemy import select

from mc_core.commands import CommandRejected, check_pump_run, expiry
from mc_core.contract.device import CmdAck
from mc_core.contract.gateway import CommandCreated

from ..context import Uow
from ..db.models import CommandRow, Device, Downlink, Gateway, Household, Plant
from ..db.types import utcnow
from ..errors import Problem, not_found
from . import alerts, devices, gateways
from .common import now_ts, to_dt, to_ts

log = logging.getLogger(__name__)

OPEN = ("queued", "delivered", "cancelling")


# --- views ---------------------------------------------------------------------


def view(c: CommandRow) -> dict:
    now = utcnow()
    # "running" is what the app shows for a delivered pump run still on.
    running = c.status == "delivered" and c.ends_at is not None and c.ends_at > now
    return {
        "id": c.id,
        "device_id": c.device_id,
        "plant_id": c.plant_id,
        "action": c.action,
        "args": c.args,
        "seconds": c.args.get("seconds"),
        "status": c.status,
        "state": "running" if running else c.status,
        "reason": c.reason,
        "source": c.source,
        "origin": c.origin,
        "rule_id": c.rule_id,
        "created_at": c.created_at,
        "exp": c.exp,
        "delivered_at": c.delivered_at,
        "ends_at": c.ends_at,
        "finished_at": c.finished_at,
    }


# --- creation (§7.1) -------------------------------------------------------------


async def _pending_pump(uow: Uow, device_id: str, slot: int) -> bool:
    rows = await uow.s.scalars(select(CommandRow).where(
        CommandRow.device_id == device_id, CommandRow.action == "pump.run",
        CommandRow.status.in_(OPEN)))
    return any(r.args.get("slot") == slot for r in rows)


async def _last_run_end(uow: Uow, device_id: str, slot: int) -> int | None:
    rows = await uow.s.scalars(select(CommandRow).where(
        CommandRow.device_id == device_id, CommandRow.action == "pump.run",
        CommandRow.status == "done").order_by(CommandRow.finished_at.desc()).limit(10))
    for r in rows:
        if r.args.get("slot") == slot:
            return to_ts(r.finished_at)
    return None


def _insert(uow: Uow, device: Device, action: str, args: dict, *, source: str,
            created_by: str | None, plant_id: str | None = None, rule_id: str | None = None,
            cancel_of: str | None = None, command_id: str | None = None,
            origin: str = "api", exp: int | None = None,
            created_at: int | None = None) -> CommandRow:
    now = created_at or now_ts()
    cmd = CommandRow(household_id=device.household_id, device_id=device.id, plant_id=plant_id,
                     action=action, args=args, status="queued", source=source, origin=origin,
                     created_by=created_by, rule_id=rule_id, cancel_of=cancel_of,
                     created_at=to_dt(now),
                     exp=to_dt(exp if exp is not None else expiry(now, device.wake_interval_s)))
    if command_id:
        cmd.id = command_id
    uow.s.add(cmd)
    return cmd


async def _require_gateway(uow: Uow, device: Device) -> list[str]:
    """409 without a usable gateway; warnings when it is offline (Api_Specs §7.1)."""
    gw = await gateways.get_gateway(uow, device.household_id)
    if gw is None or device.gateway == "none":
        raise CommandRejected("no_gateway", status=409)
    return [] if gateways.is_online(uow, gw) else ["gateway_offline"]


async def _send(uow: Uow, cmd: CommandRow) -> None:
    await uow.s.flush()
    await gateways.send_down(uow, cmd.household_id, "command", {
        "device": cmd.device_id,
        "command": {"id": cmd.id, "action": cmd.action, "exp": to_ts(cmd.exp),
                    "args": cmd.args}})
    uow.emit(cmd.household_id, "command", {"id": cmd.id, "plant_id": cmd.plant_id,
                                           "status": cmd.status})


async def create_pump_run(uow: Uow, household_id: str, plant: Plant, seconds: int, *,
                          source: str, created_by: str | None,
                          rule_id: str | None = None) -> tuple[CommandRow, list[str]]:
    """Returns the queued command and warnings (v2: `gateway_offline`)."""
    if plant.pump_device_id is None or plant.pump_slot is None:
        raise CommandRejected("slot_not_actuator", "plant has no pump")
    device = await uow.s.get(Device, plant.pump_device_id)
    if device is None or device.deleted_at is not None:
        raise CommandRejected("slot_not_actuator", "pump device removed")
    warnings = await _require_gateway(uow, device)
    check_pump_run(
        seconds, devices.actuator(device, plant.pump_slot), now=now_ts(),
        last_run_ended_at=await _last_run_end(uow, device.id, plant.pump_slot),
        pending=await _pending_pump(uow, device.id, plant.pump_slot))
    cmd = _insert(uow, device, "pump.run", {"slot": plant.pump_slot, "seconds": seconds},
                  source=source, created_by=created_by, plant_id=plant.id, rule_id=rule_id)
    await _send(uow, cmd)
    return cmd, warnings


DEVICE_ACTIONS = {
    "identify": ("device.identify", {"seconds": 10}),
    "service": ("device.service", {"minutes": 15}),
    "reboot": ("device.reboot", {}),
}


async def device_action(uow: Uow, device: Device, action: str, args: dict | None,
                        uid: str) -> CommandRow:
    if action not in DEVICE_ACTIONS:
        raise Problem(422, "unknown_action")
    await _require_gateway(uow, device)
    wire_action, defaults = DEVICE_ACTIONS[action]
    cmd = _insert(uow, device, wire_action, {**defaults, **(args or {})}, source="manual",
                  created_by=uid)
    await _send(uow, cmd)
    await uow.commit()
    return cmd


# --- cancel (§7.3) ---------------------------------------------------------------


async def get_command(uow: Uow, household_id: str, command_id: str) -> CommandRow:
    cmd = await uow.s.scalar(select(CommandRow).where(
        CommandRow.id == command_id, CommandRow.household_id == household_id))
    if cmd is None:
        raise not_found("command")
    return cmd


async def cancel(uow: Uow, household_id: str, command_id: str, uid: str) -> CommandRow:
    cmd = await get_command(uow, household_id, command_id)
    device = await uow.s.get(Device, cmd.device_id)
    if cmd.status == "queued" and cmd.sent_at is None and await _withdraw(uow, cmd):
        # Never handed to the gateway: simply don't send it.
        cmd.status, cmd.reason, cmd.finished_at = "cancelled", "withdrawn", utcnow()
    elif cmd.status == "queued":
        cmd.status = "cancelling"
        cancel_cmd = _insert(uow, device, "cmd.cancel", {"target": cmd.id}, source="manual",
                             created_by=uid, cancel_of=cmd.id, plant_id=cmd.plant_id)
        await _send(uow, cancel_cmd)
    elif cmd.status == "delivered" and cmd.action == "pump.run":
        stop = _insert(uow, device, "pump.stop", {"slot": cmd.args.get("slot")},
                       source="manual", created_by=uid, cancel_of=cmd.id, plant_id=cmd.plant_id)
        await _send(uow, stop)
    else:
        raise Problem(409, "too_late", f"command is {cmd.status}")
    uow.emit(household_id, "command", {"id": cmd.id, "plant_id": cmd.plant_id})
    await uow.commit()
    return cmd


async def _withdraw(uow: Uow, cmd: CommandRow) -> bool:
    rows = await uow.s.scalars(select(Downlink).where(
        Downlink.type == "command", Downlink.acked_at.is_(None), Downlink.sent_at.is_(None)))
    for row in rows:
        if row.body.get("command", {}).get("id") == cmd.id:
            row.acked_at, row.result = utcnow(), "superseded"
            return True
    return False


# --- acks (§7.2) -----------------------------------------------------------------


async def handle_ack(uow: Uow, device: Device, ack: CmdAck) -> None:
    cmd = await uow.s.scalar(select(CommandRow).where(
        CommandRow.id == ack.id, CommandRow.device_id == device.id))
    if cmd is None:
        log.info("ack for unknown command %s from %s", ack.id, device.id)
        return
    await _apply_ack(uow, device, cmd, ack)


async def _apply_ack(uow: Uow, device: Device, cmd: CommandRow, ack: CmdAck) -> None:
    now = utcnow()
    before = cmd.status
    if ack.status == "running":
        if cmd.status in ("queued", "cancelling"):
            cmd.status, cmd.delivered_at = "delivered", now
            cmd.ends_at = to_dt(ack.ends_at) if ack.ends_at else None
    elif ack.status == "done":
        if cmd.status in ("queued", "delivered", "cancelling"):
            cmd.status, cmd.finished_at = "done", to_dt(ack.ts) if ack.ts else now
            cmd.delivered_at = cmd.delivered_at or now
    elif ack.status == "cancelled":
        if cmd.status in ("queued", "cancelling"):
            cmd.status, cmd.finished_at = "cancelled", now
    elif ack.status in ("rejected", "failed"):
        if cmd.status in ("queued", "delivered", "cancelling"):
            expired = ack.status == "rejected" and ack.reason == "expired"
            cmd.status = "expired" if expired and before != "delivered" else "failed"
            cmd.reason, cmd.finished_at = ack.reason, now
            if cmd.status == "failed" and cmd.action == "pump.run":
                await alerts.open_alert(uow, device.household_id, "command_failed", "command",
                                        cmd.id, device.name, {"reason": ack.reason})
    if cmd.status != before:
        uow.emit(device.household_id, "command",
                 {"id": cmd.id, "plant_id": cmd.plant_id, "status": cmd.status})


# --- commands made by the gateway (rules, CLI) ---------------------------------------------


async def record_gateway_command(uow: Uow, household_id: str, msg: CommandCreated) -> None:
    if await uow.s.get(CommandRow, msg.id) is not None:
        return  # duplicate after a replay
    device = await uow.s.get(Device, msg.device)
    if device is None or device.household_id != household_id:
        log.warning("gateway command for foreign device %s", msg.device)
        return
    plant_id = None
    if msg.action == "pump.run":
        plant_id = await uow.s.scalar(select(Plant.id).where(
            Plant.household_id == household_id, Plant.pump_device_id == device.id,
            Plant.pump_slot == msg.args.get("slot"), Plant.archived_at.is_(None)))
    cmd = _insert(uow, device, msg.action, msg.args, source=msg.source, created_by=msg.rule_id,
                  plant_id=plant_id, rule_id=msg.rule_id, command_id=msg.id, origin="gateway",
                  exp=msg.exp, created_at=msg.created_at)
    cmd.sent_at = to_dt(msg.created_at)
    await uow.s.flush()
    uow.emit(household_id, "command", {"id": cmd.id, "plant_id": plant_id, "status": "queued"})


async def gateway_ack(uow: Uow, command_id: str, result: str, error: str | None) -> None:
    """`down_ack` for a command: handed to the device's session, or rejected."""
    cmd = await uow.s.get(CommandRow, command_id)
    if cmd is None:
        return
    if result == "applied":
        cmd.sent_at = cmd.sent_at or utcnow()
        return
    if cmd.status in ("queued", "cancelling"):
        cmd.status, cmd.reason, cmd.finished_at = "failed", error or "rejected", utcnow()
        device = await uow.s.get(Device, cmd.device_id)
        if cmd.action == "pump.run":
            await alerts.open_alert(uow, cmd.household_id, "command_failed", "command", cmd.id,
                                    device.name, {"reason": cmd.reason})
        uow.emit(cmd.household_id, "command",
                 {"id": cmd.id, "plant_id": cmd.plant_id, "status": cmd.status})


# --- expiry job (§7.2) ---------------------------------------------------------------


async def expire_overdue(uow: Uow) -> None:
    now = utcnow()
    rows = (await uow.s.execute(
        select(CommandRow, Device, Household.id)
        .join(Device, Device.id == CommandRow.device_id)
        .join(Household, Household.id == CommandRow.household_id)
        .where(CommandRow.status.in_(OPEN)))).all()
    # Paused while the household's gateway is offline, and one grace period
    # after it reconnected (buffered acks are still being replayed, §7.2).
    offline = await gateways.offline_households(uow)
    connected_at = dict((await uow.s.execute(select(Gateway.household_id,
                                                    Gateway.connected_at))).all())
    for cmd, device, hid in rows:
        grace = timedelta(seconds=2 * device.wake_interval_s)
        if hid in offline or (connected_at.get(hid) and now - connected_at[hid] < grace):
            continue
        if cmd.status in ("queued", "cancelling") and now > cmd.exp + grace:
            cmd.status, cmd.reason, cmd.finished_at = "expired", "no_ack", now
        elif cmd.status == "delivered" and cmd.ends_at and now > cmd.ends_at + grace:
            cmd.status, cmd.reason, cmd.finished_at = "failed", "no_final_ack", now
            if cmd.action == "pump.run":
                await alerts.open_alert(uow, hid, "command_failed", "command", cmd.id,
                                        device.name, {"reason": "no_final_ack"})
        else:
            continue
        uow.emit(hid, "command", {"id": cmd.id, "plant_id": cmd.plant_id, "status": cmd.status})
    await uow.commit()
