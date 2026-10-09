"""Token verification. Only the unsigned development verifier exists; real login is the hub's own
(Gateway/specs.md Part A §5)."""

import time
from dataclasses import dataclass

from ..errors import Problem


@dataclass(frozen=True)
class Principal:
    uid: str
    email: str | None
    email_verified: bool
    auth_time: int  # unix seconds of the last sign-in
    name: str | None = None


class TokenVerifier:
    async def verify(self, token: str, *, check_revoked: bool = False) -> Principal:
        raise NotImplementedError


class DevVerifier(TokenVerifier):
    """Accepts `dev:<uid>[:<email>]`. Only for local development and tests.

    `dev:<uid>:<email>:stale` simulates a sign-in older than 5 minutes.
    """

    async def verify(self, token: str, *, check_revoked: bool = False) -> Principal:
        parts = token.split(":")
        if len(parts) < 2 or parts[0] != "dev" or not parts[1]:
            raise Problem(401, "invalid_token")
        email = parts[2] if len(parts) > 2 and parts[2] else f"{parts[1]}@dev.local"
        stale = len(parts) > 3 and parts[3] == "stale"
        auth_time = int(time.time()) - (3600 if stale else 0)
        return Principal(parts[1], email, True, auth_time, parts[1])
