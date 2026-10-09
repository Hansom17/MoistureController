import time
from datetime import datetime, timezone


class Clock:
    """Wall clock; tests replace it with FakeClock."""

    def now(self) -> float:
        return time.time()

    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.now(), timezone.utc)


class FakeClock(Clock):
    def __init__(self, start: float = 1_800_000_000.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
