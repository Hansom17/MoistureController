"""Command checks shared by the backend and the hub (Server_Specs §7.1).

The device checks again and remains the final authority.
"""

from dataclasses import dataclass

MIN_EXPIRY_S = 15 * 60


class CommandRejected(Exception):
    """A check failed; `code` is the problem type returned to the app."""

    def __init__(self, code: str, detail: str | None = None, status: int = 422):
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class Actuator:
    """What the checks need to know about a pump slot."""

    slot: int
    max_run_s: int
    min_pause_s: int = 0
    hard_limit_s: int | None = None


def expiry(now: int, wake_interval_s: int) -> int:
    """`exp = now + max(2 × wake interval, 15 min)`."""
    return now + max(2 * wake_interval_s, MIN_EXPIRY_S)


def check_pump_run(
    seconds: int,
    actuator: Actuator | None,
    *,
    now: int,
    last_run_ended_at: int | None = None,
    pending: bool = False,
) -> None:
    """Raises [CommandRejected] if a `pump.run` must not be created."""
    if actuator is None:
        raise CommandRejected("slot_not_actuator")
    limit = actuator.max_run_s
    if actuator.hard_limit_s is not None:
        limit = min(limit, actuator.hard_limit_s)
    if seconds < 1 or seconds > limit:
        raise CommandRejected("safety_limit", f"1–{limit} s allowed")
    if (
        actuator.min_pause_s
        and last_run_ended_at is not None
        and now - last_run_ended_at < actuator.min_pause_s
    ):
        raise CommandRejected("safety_limit", f"min_pause_s {actuator.min_pause_s}")
    if pending:
        raise CommandRejected("busy", status=409)
