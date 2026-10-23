"""Everything the request handlers share."""
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bus.hub_client import HubClient
from .clock import Clock
from .config import Settings
from .errors import ApiError
from .realtime.bus import EventBus

log = logging.getLogger("mc_api")
REAUTH_TTL_S = 300
FREE_FAILURES = 5


@dataclass
class App:
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    hub: HubClient
    events: EventBus
    clock: Clock
    engine: object = None
    proofs: dict[str, tuple[str, float]] = field(default_factory=dict)      # reauth proof -> (user id, expiry)
    failures: dict[str, tuple[int, float]] = field(default_factory=dict)    # login key -> (count, locked until)

    # ---- login rate limit: 5 free failures, then 1 s, 2 s, 4 s ... up to 5 minutes -----------------
    def check_login_allowed(self, key: str) -> None:
        count, until = self.failures.get(key, (0, 0.0))
        now = self.clock.now()
        if until > now:
            raise ApiError("rate_limited", "Too many failed logins", f"try again in {int(until - now) + 1} s",
                           retry_after=int(until - now) + 1)

    def login_failed(self, key: str) -> None:
        count, _ = self.failures.get(key, (0, 0.0))
        count += 1
        delay = 0 if count <= FREE_FAILURES else min(300, 2 ** (count - FREE_FAILURES - 1))
        self.failures[key] = (count, self.clock.now() + delay)

    def login_ok(self, key: str) -> None:
        self.failures.pop(key, None)

    # ---- reauth proofs ------------------------------------------------------------------------------
    def issue_proof(self, user_id: str, proof: str) -> None:
        now = self.clock.now()
        self.proofs = {k: v for k, v in self.proofs.items() if v[1] > now}
        self.proofs[proof] = (user_id, now + REAUTH_TTL_S)

    def check_proof(self, user_id: str, proof: str | None) -> None:
        entry = self.proofs.get(proof or "")
        if entry is None or entry[0] != user_id or entry[1] < self.clock.now():
            raise ApiError("reauth_required", "Enter your password to continue")
