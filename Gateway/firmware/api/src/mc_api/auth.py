"""Bearer-token authentication and role checks (Gateway/specs.md section 5)."""
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select

from .db.models import AuditLog, Token, User
from .errors import ApiError
from .security import sha256
from .state import App

ROLES = ["viewer", "member", "admin", "owner"]
LAST_USED_EVERY_S = 60


def rank(role: str) -> int:
    return ROLES.index(role)


@dataclass
class Principal:
    user_id: str
    username: str
    display_name: str
    role: str
    token_id: str

    @property
    def actor(self) -> dict:
        return {"user_id": self.user_id, "role": self.role}


def app_of(request: Request) -> App:
    return request.app.state.mc


async def current(request: Request) -> Principal:
    app = app_of(request)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer ") or len(header) < 12:
        raise ApiError("unauthorized", "Sign in first")
    th = sha256(header[7:].strip())
    now = int(app.clock.now())
    async with app.sessions() as s:
        row = (await s.execute(select(Token, User).join(User, User.id == Token.user_id)
                               .where(Token.token_hash == th))).first()
        if row is None or row[0].revoked_at is not None or row[1].disabled_at is not None:
            raise ApiError("unauthorized", "Sign in again")
        tok, user = row
        if tok.last_used_at is None or now - tok.last_used_at >= LAST_USED_EVERY_S:
            tok.last_used_at = now
            await s.commit()
        return Principal(user.id, user.username, user.display_name, user.role, tok.id)


def require(role: str):
    async def dep(p: Principal = Depends(current)) -> Principal:
        if rank(p.role) < rank(role):
            raise ApiError("forbidden", "Your role does not allow this", f"{role} or higher is required")
        return p
    return dep


def reauth(request: Request, p: Principal) -> None:
    app_of(request).check_proof(p.user_id, request.headers.get("x-mc-reauth"))


async def audit(app: App, actor: str, action: str, detail: dict | None = None, request: Request | None = None) -> None:
    ip = request.client.host if request is not None and request.client else None
    async with app.sessions() as s:
        s.add(AuditLog(actor=actor, action=action, detail=detail, ts=int(app.clock.now()), ip=ip))
        await s.commit()
