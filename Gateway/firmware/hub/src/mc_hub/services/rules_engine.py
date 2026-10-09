"""Rule decisions (pure; ported from the previous implementation, Gateway/specs.md section 12)."""
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class RuleSpec:
    id: str
    plant_id: str
    enabled: bool
    threshold: float
    water_s: int
    cooldown_s: int
    max_per_day: int
    quiet_from: str | None = None
    quiet_to: str | None = None


@dataclass(frozen=True)
class RuleContext:
    now: int
    timezone: str
    has_pump: bool
    last_rule_cmd_at: int | None
    rule_cmds_today: int
    pending_command: bool
    clock_synced: bool = True


@dataclass(frozen=True)
class Decision:
    decision: str                  # "water" | "skip"
    skip_reason: str | None = None


def _hm(v: str) -> time:
    h, m = v.split(":")
    return time(int(h), int(m))


def in_quiet_hours(rule: RuleSpec, now: int, tz: str) -> bool:
    if not rule.quiet_from or not rule.quiet_to:
        return False
    local = datetime.fromtimestamp(now, ZoneInfo(tz)).time()
    start, end = _hm(rule.quiet_from), _hm(rule.quiet_to)
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def start_of_day(now: int, tz: str) -> int:
    local = datetime.fromtimestamp(now, ZoneInfo(tz))
    return int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def evaluate(rule: RuleSpec, value: float | None, sensor_error: str | None, ctx: RuleContext) -> Decision | None:
    """None: nothing to record (disabled, or the plant is wet enough)."""
    if not rule.enabled:
        return None
    if sensor_error not in (None, "ok") or value is None:
        return Decision("skip", "sensor_error")
    if value >= rule.threshold:
        return None
    if not ctx.clock_synced:
        return Decision("skip", "clock_not_synced")
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
