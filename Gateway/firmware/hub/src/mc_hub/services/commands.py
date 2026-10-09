"""Commands (Gateway/specs.md section 9): creation checks, cancel, lifecycle from device acks."""
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from mc_hub.db.models import Command, Device, Plant, Setting
from mc_hub.errors import HubError

from . import alerts
from .effects import Effects
from .views import alert_view

DEFAULT_TTL_S = 900
HARD_LIMIT_S = 300           # no pump run longer than this, whatever the device says
OPEN = ("queued", "delivered", "cancelling")
PUMP_ACTIONS = ("pump.run", "pump.stop")
NOT_NEW = ("ready", "online", "late", "offline", "safe_mode")
DEVICE_ACTIONS = {"identify": "device.identify", "reboot": "device.reboot", "clear_safe_mode": "device.clear_safe_mode"}


def command_view(c: Command) -> dict:
    return {
        "id": c.id, "device_id": c.device_id, "plant_id": c.plant_id, "action": c.action, "args": c.args or {},
        "status": c.status, "reason": c.reason, "source": c.source, "created_by": c.created_by, "rule_id": c.rule_id,
        "created_at": c.created_at, "exp": c.exp, "sent_at": c.sent_at, "delivered_at": c.delivered_at,
        "finished_at": c.finished_at, "ends_at": c.ends_at, "cancel_of": c.cancel_of, "updated_at": c.updated_at,
    }


async def next_zb_id(s: AsyncSession) -> int:
    row = await s.get(Setting, "zb_counter")
    n = ((row.value if row else 0) % (2**32 - 1)) + 1
    if row is None:
        s.add(Setting(key="zb_counter", value=n))
    else:
        row.value = n
    return n


def pump_config(d: Device, slot: int) -> dict | None:
    """The pump entry of the slot in the configuration the device reports running."""
    for sl in (d.reported_config or {}).get("slots", []):
        if sl.get("slot") == slot and sl.get("module") == "pump":
            return sl
    return None


async def _open_pump_command(s: AsyncSession, device_id: str, slot: int) -> Command | None:
    rows = (await s.execute(select(Command).where(
        Command.device_id == device_id, Command.status.in_(OPEN), Command.action.in_(PUMP_ACTIONS)))).scalars()
    for c in rows:
        if (c.args or {}).get("slot") == slot and c.action == "pump.run":
            return c
    return None


async def _last_run_end(s: AsyncSession, device_id: str, slot: int) -> int | None:
    rows = (await s.execute(select(Command).where(
        Command.device_id == device_id, Command.action == "pump.run", Command.status == "done")
        .order_by(Command.finished_at.desc()).limit(20))).scalars()
    for c in rows:
        if (c.args or {}).get("slot") == slot:
            return c.finished_at
    return None


def _new(ctx_now: int, device_id: str, action: str, args: dict, *, zb_id: int, ttl_s: int, source: str,
         created_by: str | None, request_id: str | None, plant_id: str | None = None,
         rule_id: str | None = None, cancel_of: str | None = None) -> Command:
    return Command(id=str(ULID()), zb_id=zb_id, device_id=device_id, plant_id=plant_id, action=action, args=args,
                   status="queued", source=source, created_by=created_by, rule_id=rule_id, request_id=request_id,
                   created_at=ctx_now, exp=ctx_now + ttl_s, cancel_of=cancel_of, updated_at=ctx_now)


def _check_device(d: Device | None, *, allow_safe_mode: bool = False) -> Device:
    if d is None or d.deleted_at is not None:
        raise HubError("not_found", "Device not found")
    if d.status not in NOT_NEW:
        raise HubError("device_not_ready", detail=f"device is {d.status}")
    if d.status == "safe_mode" and not allow_safe_mode:
        raise HubError("device_safe_mode")
    return d


def _ttl(ttl_s: int | None) -> int:
    ttl = DEFAULT_TTL_S if ttl_s is None else int(ttl_s)
    if not 30 <= ttl <= 86400:
        raise HubError("validation", detail="ttl_s must be 30..86400")
    return ttl


async def create_pump_run(s: AsyncSession, fx: Effects, now: int, d: Device | None, slot: int, seconds: int, *,
                          source: str, created_by: str | None, request_id: str | None, plant_id: str | None = None,
                          rule_id: str | None = None, ttl_s: int | None = None) -> Command:
    d = _check_device(d)
    act = pump_config(d, slot)
    if act is None:
        raise HubError("slot_not_actuator", detail=f"slot {slot} is not a pump in the reported configuration")
    limit = min(int(act.get("max_run_s", HARD_LIMIT_S)), HARD_LIMIT_S)
    if not 1 <= seconds <= limit:
        raise HubError("safety_limit", detail=f"1..{limit} s allowed")
    last_end = await _last_run_end(s, d.id, slot)
    pause = int(act.get("min_pause_s", 0))
    if pause and last_end is not None and now - last_end < pause:
        raise HubError("safety_limit", detail=f"min_pause_s {pause}")
    if await _open_pump_command(s, d.id, slot) is not None:
        raise HubError("busy", "Pump is busy", "A pump command for this slot is queued or running.")
    c = _new(now, d.id, "pump.run", {"slot": slot, "seconds": seconds}, zb_id=await next_zb_id(s),
             ttl_s=_ttl(ttl_s), source=source, created_by=created_by, request_id=request_id,
             plant_id=plant_id, rule_id=rule_id)
    s.add(c)
    await s.flush()
    fx.emit("command", command_view(c))
    fx.kick(d.id)
    return c


async def create_device_action(s: AsyncSession, fx: Effects, now: int, d: Device | None, action: str, *,
                               created_by: str | None, request_id: str | None, arg: int = 0) -> Command:
    if action not in DEVICE_ACTIONS:
        raise HubError("validation", detail=f"action must be one of {sorted(DEVICE_ACTIONS)}")
    d = _check_device(d, allow_safe_mode=True)
    c = _new(now, d.id, DEVICE_ACTIONS[action], {"arg": arg}, zb_id=await next_zb_id(s), ttl_s=DEFAULT_TTL_S,
             source="manual", created_by=created_by, request_id=request_id)
    s.add(c)
    await s.flush()
    fx.emit("command", command_view(c))
    fx.kick(d.id)
    return c


async def cancel(s: AsyncSession, fx: Effects, now: int, command_id: str, *, created_by: str | None,
                 request_id: str | None) -> Command:
    c = await s.get(Command, command_id)
    if c is None:
        raise HubError("not_found", "Command not found")
    if c.status not in ("queued", "delivered"):
        raise HubError("conflict", "Command is already finished" if c.status != "cancelling" else "Already cancelling")
    if c.status == "queued" and c.sent_at is None:
        c.status, c.finished_at, c.updated_at = "cancelled", now, now
        fx.emit("command", command_view(c))
        return c
    d = await s.get(Device, c.device_id)
    if d is None or d.deleted_at is not None:
        raise HubError("not_found", "Device not found")
    if c.status == "delivered" and c.action == "pump.run":
        stop = _new(now, d.id, "pump.stop", {"slot": c.args["slot"]}, zb_id=await next_zb_id(s), ttl_s=DEFAULT_TTL_S,
                    source="manual", created_by=created_by, request_id=request_id, plant_id=c.plant_id,
                    cancel_of=c.id)
    else:
        stop = _new(now, d.id, "cmd.cancel", {"target": c.zb_id}, zb_id=await next_zb_id(s), ttl_s=DEFAULT_TTL_S,
                    source="manual", created_by=created_by, request_id=request_id, plant_id=c.plant_id,
                    cancel_of=c.id)
    s.add(stop)
    c.status, c.updated_at = "cancelling", now
    await s.flush()
    fx.emit("command", command_view(c))
    fx.emit("command", command_view(stop))
    fx.kick(d.id)
    return c


# ---- lifecycle from device acks (9.2) ---------------------------------------------------------

async def apply_ack(s: AsyncSession, fx: Effects, now: int, d: Device, ack) -> None:
    if d.last_ack_n is not None and ack.n == d.last_ack_n:
        return
    d.last_ack_n = ack.n
    c = (await s.execute(select(Command).where(Command.zb_id == ack.cmd_id))).scalar_one_or_none()
    if c is None or c.device_id != d.id:
        return
    before = c.status
    if ack.state == "running":
        if c.status == "queued":
            c.status, c.delivered_at = "delivered", now
            c.ends_at = now + int(ack.ends_in_s or 0)
    elif ack.state == "done":
        if c.status in OPEN:
            c.status, c.finished_at = "done", now
    elif ack.state == "cancelled":
        if c.status in ("queued", "cancelling", "delivered"):
            c.status, c.finished_at = "cancelled", now
    elif ack.state in ("rejected", "failed"):
        if c.status in OPEN:
            c.reason = ack.reason
            if ack.state == "rejected" and ack.reason == "expired":
                c.status, c.finished_at = "expired", now
            else:
                c.status, c.finished_at = "failed", now
    if c.status == before:
        return
    c.updated_at = now
    if c.status == "failed" and c.action == "pump.run":
        a, new = await alerts.open_alert(s, now, "command_failed", "command", c.id, d.name or d.id, "warning",
                                         {"reason": c.reason, "device_id": d.id})
        if new:
            fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
            fx.notify(f"Watering failed on {d.name or d.id}: {c.reason}", [], "alert", alert_kind="command_failed")
        await _notify_rule(s, fx, c, "failed", f"Watering failed ({c.reason})")
    if c.status in ("done", "cancelled", "expired", "failed") and c.cancel_of:
        # the cancelling command finished; the target gets its own ack from the device
        pass
    fx.emit("command", command_view(c))
    fx.kick(d.id)


async def _notify_rule(s: AsyncSession, fx: Effects, c: Command, trigger: str, text: str) -> None:
    if not c.rule_id:
        return
    from mc_hub.db.models import Rule
    r = await s.get(Rule, c.rule_id)
    if r is not None and trigger in (r.notify_on or []):
        plant = await s.get(Plant, c.plant_id) if c.plant_id else None
        fx.notify(f"{plant.name if plant else 'Plant'}: {text}", list(r.notify_channels or []), "rule",
                  trigger=trigger)
