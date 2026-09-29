"""Cloud rules for households without a hub (Server_Specs §11.1)."""

import logging
from datetime import timedelta

from sqlalchemy import func, select

from mc_core.commands import CommandRejected
from mc_core.rules import RuleContext, RuleSpec, evaluate, start_of_day

from ..context import Uow
from ..db.models import CommandRow, Household, Plant, Rule, RuleExecution
from ..db.types import utcnow
from . import alerts
from .commands import OPEN, create_pump_run
from .common import now_ts, to_dt, to_ts

log = logging.getLogger(__name__)


def spec(r: Rule) -> RuleSpec:
    return RuleSpec(id=r.id, plant_id=r.plant_id, enabled=r.enabled, threshold=r.threshold,
                    water_s=r.water_s, cooldown_s=r.cooldown_s, max_per_day=r.max_per_day,
                    quiet_from=r.quiet_from, quiet_to=r.quiet_to)


async def _context(uow: Uow, household: Household, plant: Plant, now: int) -> RuleContext:
    last = await uow.s.scalar(select(func.max(CommandRow.created_at)).where(
        CommandRow.plant_id == plant.id, CommandRow.source == "rule"))
    today = await uow.s.scalar(select(func.count()).where(
        CommandRow.plant_id == plant.id, CommandRow.source == "rule",
        CommandRow.created_at >= to_dt(start_of_day(now, household.timezone))))
    pending = False
    if plant.pump_device_id is not None:
        rows = await uow.s.scalars(select(CommandRow).where(
            CommandRow.device_id == plant.pump_device_id, CommandRow.action == "pump.run",
            CommandRow.status.in_(OPEN)))
        pending = any(r.args.get("slot") == plant.pump_slot for r in rows)
    return RuleContext(now=now, timezone=household.timezone,
                       has_pump=plant.pump_device_id is not None, last_rule_cmd_at=to_ts(last),
                       rule_cmds_today=today or 0, pending_command=pending)


async def run_for_reading(uow: Uow, household: Household, plant: Plant, value: float | None,
                          error: str | None, reading_ref: dict) -> None:
    now = now_ts()
    for rule in await uow.s.scalars(select(Rule).where(Rule.plant_id == plant.id)):
        decision = evaluate(spec(rule), value, error, await _context(uow, household, plant, now))
        if decision is None:
            continue
        execution = RuleExecution(household_id=household.id, rule_id=rule.id, plant_id=plant.id,
                                  ts=utcnow(), reading_ref=reading_ref,
                                  decision=decision.decision, skip_reason=decision.skip_reason,
                                  origin="cloud")
        if decision.water:
            try:
                cmd, _ = await create_pump_run(uow, household.id, plant, rule.water_s,
                                               source="rule", created_by=rule.id,
                                               rule_id=rule.id)
                execution.command_id = cmd.id
            except CommandRejected as e:
                # Checks from the command service (e.g. min pause) still apply.
                execution.decision, execution.skip_reason = "skip", e.code
        uow.s.add(execution)
        if execution.skip_reason == "daily_limit":
            await _check_limit_two_days(uow, household, plant, rule, now)
        uow.emit(household.id, "rule_execution", {"plant_id": plant.id, "rule_id": rule.id})


async def _check_limit_two_days(uow: Uow, household: Household, plant: Plant, rule: Rule,
                                now: int) -> None:
    """`rule_limit_reached` when the daily limit is hit on 2 consecutive days."""
    today = to_dt(start_of_day(now, household.timezone))
    yesterday = today - timedelta(days=1)
    hit = await uow.s.scalar(select(func.count()).where(
        RuleExecution.rule_id == rule.id, RuleExecution.skip_reason == "daily_limit",
        RuleExecution.ts >= yesterday, RuleExecution.ts < today))
    if hit:
        await alerts.open_alert(uow, household.id, "rule_limit_reached", "plant", plant.id,
                                plant.name, {"rule_id": rule.id})
