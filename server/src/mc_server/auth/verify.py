"""ID token verification (Server_Specs §5.1)."""

import asyncio
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


class FirebaseVerifier(TokenVerifier):
    def __init__(self, credentials_path: str | None, project_id: str | None):
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(credentials_path) if credentials_path else None
        options = {"projectId": project_id} if project_id else None
        self.app = firebase_admin.initialize_app(cred, options, name="mc")

    async def verify(self, token: str, *, check_revoked: bool = False) -> Principal:
        from firebase_admin import auth

        try:
            claims = await asyncio.to_thread(
                auth.verify_id_token, token, app=self.app, check_revoked=check_revoked)
        except auth.RevokedIdTokenError as e:
            raise Problem(401, "session_revoked") from e
        except auth.UserDisabledError as e:
            raise Problem(401, "account_disabled") from e
        except Exception as e:
            raise Problem(401, "invalid_token") from e
        return Principal(
            uid=claims["uid"],
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified")),
            auth_time=int(claims.get("auth_time", 0)),
            name=claims.get("name"),
        )
