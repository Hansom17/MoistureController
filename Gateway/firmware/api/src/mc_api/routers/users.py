"""Users, invites, ownership and the audit log (Gateway/specs.md 5.3 - 5.5)."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from ulid import ULID

from mc_api.auth import Principal, app_of, audit, rank, reauth, require
from mc_api.convert import iso
from mc_api.db.models import AuditLog, Invite, Token, User
from mc_api.errors import ApiError
from mc_api.security import hash_password, new_code, sha256

from .meta_auth import check_password, check_username, new_session_token, user_view

router = APIRouter()
ASSIGNABLE_BY_ADMIN = ("viewer", "member")
DEFAULT_INVITE_S = 48 * 3600


@router.get("/users")
async def list_users(request: Request, p: Principal = Depends(require("viewer"))):
    async with app_of(request).sessions() as s:
        rows = (await s.execute(select(User).order_by(User.created_at))).scalars()
        return [user_view(u) for u in rows]


def _can_manage(p: Principal, target: User, new_role: str | None = None) -> None:
    """Admins manage members and viewers up to `member`; only the owner touches admins."""
    if target.role == "owner":
        raise ApiError("forbidden", "The owner cannot be changed or removed")
    if p.role == "owner":
        if new_role == "owner":
            raise ApiError("validation", detail="use transfer-ownership to hand over the gateway")
        return
    if target.role not in ASSIGNABLE_BY_ADMIN:
        raise ApiError("forbidden", "Only the owner can change admins")
    if new_role is not None and new_role not in ASSIGNABLE_BY_ADMIN:
        raise ApiError("forbidden", "Admins can assign viewer and member only")


class UserPatch(BaseModel):
    role: str | None = None
    display_name: str | None = None
    disabled: bool | None = None


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserPatch, request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    if body.role is not None and body.role not in ("viewer", "member", "admin"):
        raise ApiError("validation", detail="role must be viewer, member or admin")
    async with app.sessions() as s:
        u = await s.get(User, user_id)
        if u is None:
            raise ApiError("not_found", "User not found")
        _can_manage(p, u, body.role)
        # changing an admin's role (or making one) is a sensitive action
        if (u.role == "admin" and body.role not in (None, "admin")) or body.role == "admin":
            reauth(request, p)
        changes = {}
        if body.role is not None and body.role != u.role:
            changes["role"] = [u.role, body.role]
            u.role = body.role
        if body.display_name is not None:
            u.display_name = body.display_name.strip()[:80] or u.username
        if body.disabled is not None:
            u.disabled_at = int(app.clock.now()) if body.disabled else None
            changes["disabled"] = body.disabled
            if body.disabled:
                await s.execute(update(Token).where(Token.user_id == u.id, Token.revoked_at.is_(None))
                                .values(revoked_at=int(app.clock.now())))
        await s.commit()
        view = user_view(u)
    if body.disabled:
        app.events.close_user(user_id)
    await audit(app, p.user_id, "user_updated", {"user": user_id, **changes}, request)
    return view


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: str, request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    async with app.sessions() as s:
        u = await s.get(User, user_id)
        if u is None:
            raise ApiError("not_found", "User not found")
        _can_manage(p, u)
        if u.role == "admin":
            reauth(request, p)
        for t in (await s.execute(select(Token).where(Token.user_id == u.id))).scalars():
            await s.delete(t)
        await s.delete(u)
        await s.commit()
    app.events.close_user(user_id)
    await app.hub.publish_event("user_removed", {"user_id": user_id})
    await audit(app, p.user_id, "user_removed", {"user": user_id, "username": u.username}, request)


class TransferIn(BaseModel):
    user_id: str


@router.post("/transfer-ownership")
async def transfer_ownership(body: TransferIn, request: Request, p: Principal = Depends(require("owner"))):
    app = app_of(request)
    reauth(request, p)
    async with app.sessions() as s:
        new = await s.get(User, body.user_id)
        if new is None or new.disabled_at is not None or new.id == p.user_id:
            raise ApiError("validation", detail="pick another active user")
        old = await s.get(User, p.user_id)
        old.role = "admin"
        await s.flush()
        new.role = "owner"
        await s.commit()
    await audit(app, p.user_id, "ownership_transferred", {"to": body.user_id}, request)
    return {"owner": body.user_id}


# ---- invites ----------------------------------------------------------------------------------------

def invite_view(i: Invite, now: int) -> dict:
    status = "used" if i.used_at else "revoked" if i.revoked_at else "expired" if i.expires_at < now else "open"
    return {"id": i.id, "role": i.role, "created_by": i.created_by, "created_at": iso(i.created_at),
            "expires_at": iso(i.expires_at), "status": status, "used_by": i.used_by}


class InviteIn(BaseModel):
    role: str = "member"
    expires_in: int = DEFAULT_INVITE_S


@router.post("/invites", status_code=201)
async def create_invite(body: InviteIn, request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    allowed = ("viewer", "member", "admin") if p.role == "owner" else ASSIGNABLE_BY_ADMIN
    if body.role not in allowed:
        raise ApiError("forbidden", f"You can invite: {', '.join(allowed)}")
    if not 300 <= body.expires_in <= 30 * 86400:
        raise ApiError("validation", detail="expires_in must be 300 s .. 30 days")
    code, now = new_code(), int(app.clock.now())
    async with app.sessions() as s:
        inv = Invite(id=str(ULID()), code_hash=sha256(code), role=body.role, created_by=p.user_id, created_at=now,
                     expires_at=now + body.expires_in)
        s.add(inv)
        await s.commit()
        view = invite_view(inv, now)
    await audit(app, p.user_id, "invite_created", {"invite": inv.id, "role": body.role}, request)
    return {**view, "code": code, "path": f"/join#c={code}"}     # the code is shown once


@router.get("/invites")
async def list_invites(request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    now = int(app.clock.now())
    async with app.sessions() as s:
        rows = (await s.execute(select(Invite).order_by(Invite.created_at.desc()))).scalars()
        return [invite_view(i, now) for i in rows]


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_invite(invite_id: str, request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    async with app.sessions() as s:
        i = await s.get(Invite, invite_id)
        if i is None:
            raise ApiError("not_found", "Invite not found")
        i.revoked_at = i.revoked_at or int(app.clock.now())
        await s.commit()
    await audit(app, p.user_id, "invite_revoked", {"invite": invite_id}, request)


async def _open_invite(app, s, code: str) -> Invite:
    inv = (await s.execute(select(Invite).where(Invite.code_hash == sha256(code.strip().upper())))).scalar_one_or_none()
    if inv is None or inv.used_at or inv.revoked_at or inv.expires_at < int(app.clock.now()):
        raise ApiError("invalid_invite", "This invite is not valid (anymore)")
    return inv


@router.get("/invites/{code}")
async def preview_invite(code: str, request: Request):
    app = app_of(request)
    async with app.sessions() as s:
        inv = await _open_invite(app, s, code)
    return {"role": inv.role, "installation": (app.hub.state.get("installation") or {}).get("name", ""),
            "expires_at": iso(inv.expires_at)}


class AcceptIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    device_name: str = ""


@router.post("/invites/{code}/accept", status_code=201)
async def accept_invite(code: str, body: AcceptIn, request: Request):
    app = app_of(request)
    username, _ = check_username(body.username), check_password(body.password)
    async with app.sessions() as s:
        inv = await _open_invite(app, s, code)
        if (await s.execute(select(User).where(User.username == username))).scalar_one_or_none():
            raise ApiError("conflict", "That username is taken")
        now = int(app.clock.now())
        user = User(id=str(ULID()), username=username, password_hash=hash_password(body.password), role=inv.role,
                    display_name=body.display_name or username, created_at=now)
        s.add(user)
        await s.flush()
        inv.used_by, inv.used_at = user.id, now
        raw, tok = await new_session_token(app, s, user, body.device_name)
        await s.commit()
    await audit(app, user.id, "invite_accepted", {"invite": inv.id, "role": inv.role}, request)
    return {"token": raw, "token_id": tok.id, "user": user_view(user)}


# ---- audit ------------------------------------------------------------------------------------------

@router.get("/audit")
async def audit_log(request: Request, limit: int = 100, before: int | None = None,
                    p: Principal = Depends(require("admin"))):
    limit = max(1, min(limit, 500))
    async with app_of(request).sessions() as s:
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if before:
            q = q.where(AuditLog.id < before)
        rows = (await s.execute(q)).scalars().all()
        return {"items": [{"id": r.id, "actor": r.actor, "action": r.action, "detail": r.detail, "ts": iso(r.ts),
                           "ip": r.ip} for r in rows],
                "next": rows[-1].id if len(rows) == limit else None}
