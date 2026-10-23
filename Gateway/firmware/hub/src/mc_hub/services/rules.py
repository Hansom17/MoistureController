"""Rule evaluation after a reading is stored (Gateway/specs.md section 12)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mc_hub.db.models import Command, Device, Plant, Reading, Rule, RuleExecution, Setting
from mc_hub.errors import HubError

from . import commands
from .effects import Effects
from .rules_engine import RuleContext, RuleSpec, evaluate, start_of_day

SKIP_PROBLEMS = ("sensor_error", "no_pump", "clock_not_synced", "battery_critical")
BLOCK_TO_SKIP = {"busy": "pending_command", "slot_not_actuator": "no_pump", "device_not_ready": "no_pump",
                 "device_safe_mode": "no_pump", "safety_limit": "daily_limit", "battery_critical": "battery_critical"}


async def evaluate_reading(s: AsyncSession, fx: Effects, now: int, reading: Reading, clock_synced: bool = True) -> None:
    if reading.plant_id is None:
        return
    plant = await s.get(Plant, reading.plant_id)
    if plant is None or plant.archived_at is not None:
        return
    rules = (await s.execute(select(Rule).where(Rule.plant_id == plant.id, Rule.deleted_at.is_(None)))).scalars().all()
    if not rules:
        return
    tz_row = await s.get(Setting, "timezone")
    tz = (tz_row.value if tz_row else None) or "UTC"
    for rule in rules:
        pump = await s.get(Device, plant.pump_device_id) if plant.pump_device_id else None
        has_pump = pump is not None and pump.deleted_at is None and plant.pump_slot is not None
        spec = RuleSpec(rule.id, plant.id, rule.enabled, rule.threshold, rule.water_s, rule.cooldown_s,
                        rule.max_per_day, rule.quiet_from, rule.quiet_to)
        ctx = RuleContext(now, tz, has_pump, await _last_rule_cmd(s, rule.id),
                          await _cmds_today(s, rule.id, now, tz), await _pending(s, plant) if has_pump else False,
                          clock_synced)
        decision = evaluate(spec, reading.value, reading.error, ctx)
        if decision is None:
            continue
        command = None
        reason = decision.skip_reason
        if decision.decision == "water":
            try:
                command = await commands.create_pump_run(s, fx, now, pump, plant.pump_slot, rule.water_s,
                                                         source="rule", created_by=None, request_id=None,
                                                         plant_id=plant.id, rule_id=rule.id)
            except HubError as e:
                reason = BLOCK_TO_SKIP.get(e.type, "pending_command")
        s.add(RuleExecution(rule_id=rule.id, plant_id=plant.id, ts=now, reading_ref=reading.id,
                            decision="water" if command else "skip", skip_reason=None if command else reason,
                            command_id=command.id if command else None))
        fx.emit("rule", {"rule_id": rule.id, "execution": {"decision": "water" if command else "skip",
                                                           "skip_reason": None if command else reason, "ts": now}})
        if command is not None and "watered" in (rule.notify_on or []):
            fx.notify(f"{plant.name}: watering {rule.water_s} s (moisture {reading.value:.0f}%)",
                      list(rule.notify_channels or []), "rule", trigger="watered")
        if command is None and reason in SKIP_PROBLEMS and "skipped_problem" in (rule.notify_on or []):
            fx.notify(f"{plant.name}: rule skipped ({reason})", list(rule.notify_channels or []), "rule",
                      trigger="skipped_problem")


async def _last_rule_cmd(s: AsyncSession, rule_id: str) -> int | None:
    return (await s.execute(select(func.max(Command.created_at)).where(
        Command.rule_id == rule_id, Command.status != "expired"))).scalar()


async def _cmds_today(s: AsyncSession, rule_id: str, now: int, tz: str) -> int:
    return (await s.execute(select(func.count()).select_from(Command).where(
        Command.rule_id == rule_id, Command.created_at >= start_of_day(now, tz)))).scalar() or 0


async def _pending(s: AsyncSession, plant: Plant) -> bool:
    rows = (await s.execute(select(Command).where(
        Command.device_id == plant.pump_device_id, Command.action == "pump.run",
        Command.status.in_(commands.OPEN)))).scalars()
    return any((c.args or {}).get("slot") == plant.pump_slot for c in rows)
