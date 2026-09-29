"""Rules engine shared by the backend and the hub (Server_Specs §11.1).

Pure functions: callers gather the context (last rule command, count today,
pending commands) from their own storage and act on the decision.
"""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

SkipReason = Literal[
    "sensor_error", "no_pump", "quiet_hours", "cooldown", "daily_limit", "pending_command"
]


@dataclass(frozen=True)
class RuleSpec:
    id: str
    plant_id: str
    enabled: bool
    threshold: float
    water_s: int
    cooldown_s: int
    max_per_day: int
    quiet_from: str | None = None  # "HH:MM", household timezone
    quiet_to: str | None = None


@dataclass(frozen=True)
class RuleContext:
    now: int  # unix seconds
    timezone: str
    has_pump: bool
    last_rule_cmd_at: int | None
    rule_cmds_today: int
    pending_command: bool


@dataclass(frozen=True)
class Decision:
    decision: Literal["water", "skip"]
    skip_reason: SkipReason | None = None

    @property
    def water(self) -> bool:
        return self.decision == "water"


def _parse_hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def in_quiet_hours(rule: RuleSpec, now: int, timezone: str) -> bool:
    if not rule.quiet_from or not rule.quiet_to:
        return False
    local = datetime.fromtimestamp(now, ZoneInfo(timezone)).time()
    start, end = _parse_hm(rule.quiet_from), _parse_hm(rule.quiet_to)
    if start <= end:
        return start <= local < end
    return local >= start or local < end  # spans midnight, e.g. 22:00–07:00


def start_of_day(now: int, timezone: str) -> int:
    """Unix time of local midnight "today" in the household timezone."""
    local = datetime.fromtimestamp(now, ZoneInfo(timezone))
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def evaluate(
    rule: RuleSpec,
    value: float | None,
    sensor_error: str | None,
    ctx: RuleContext,
) -> Decision | None:
    """Decision for one new reading, or None if the rule doesn't trigger.

    None means "nothing to log": rule disabled or value at/above threshold.
    Any other outcome is recorded as a rule execution.
    """
    if not rule.enabled:
        return None
    if sensor_error is not None or value is None:
        # An erroring sensor has no value to compare; log it so the user sees
        # why nothing happened.
        return Decision("skip", "sensor_error")
    if value >= rule.threshold:
        return None
    if not ctx.has_pump:
        return Decision("skip", "no_pump")
    if in_quiet_hours(rule, ctx.now, ctx.timezone):
        return Decision("skip", "quiet_hours")
    if ctx.last_rule_cmd_at is not None and ctx.now - ctx.last_rule_cmd_at < rule.cooldown_s:
        return Decision("skip", "cooldown")
    if ctx.rule_cmds_today >= rule.max_per_day:
        return Decision("skip", "daily_limit")
    if ctx.pending_command:
        return Decision("skip", "pending_command")
    return Decision("water")
