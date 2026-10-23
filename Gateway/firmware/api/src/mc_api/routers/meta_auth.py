"""Setup, login, tokens, reauth and the user's own profile."""
import logging
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from ulid import ULID

from mc_api import CONTRACT, __version__
from mc_api.auth import Principal, app_of, audit, current, require
from mc_api.convert import iso
from mc_api.db.models import Setting, Token, User
from mc_api.errors import ApiError
from mc_api.security import hash_password, new_code, new_token, sha256, verify_password

log = logging.getLogger("mc_api")
router = APIRouter()
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def user_view(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "created_at": iso(u.created_at), "disabled": u.disabled_at is not None}


def check_username(name: str) -> str:
    n = name.strip().lower()
    if not USERNAME.match(n):
        raise ApiError("validation", detail="username: 3-32 characters, a-z 0-9 . _ -")
    return n


def check_password(pw: str) -> str:
    if len(pw) < 8:
        raise ApiError("validation", detail="password: at least 8 characters")
    return pw


async def new_session_token(app, s, user: User, name: str) -> tuple[str, Token]:
    raw = new_token()
    tok = Token(id=str(ULID()), user_id=user.id, token_hash=sha256(raw), name=name or "unnamed device",
                created_at=int(app.clock.now()))
    s.add(tok)
    return raw, tok


async def setup_code(app) -> str | None:
    """The one-time setup code, created on first start (and by `reset-owner`)."""
    async with app.sessions() as s:
        owners = (await s.execute(select(func.count()).select_from(User).where(User.role == "owner"))).scalar()
        reset = await s.get(Setting, "owner_reset")
        code = await s.get(Setting, "setup_code")
        if owners and not (reset and reset.value):
            if code is not None:
                await s.delete(code)
                await s.commit()
            return None
        if code is None:
            code = Setting(key="setup_code", value=new_code())
            s.add(code)
            await s.commit()
            log.warning("SETUP CODE: %s  (open the web app to set up this gateway)", code.value)
        return code.value


# ---- meta -------------------------------------------------------------------------------------------

@router.get("/meta")
async def meta(request: Request):
    app = app_of(request)
    async with app.sessions() as s:
        owners = (await s.execute(select(func.count()).select_from(User).where(User.role == "owner"))).scalar()
        reset = await s.get(Setting, "owner_reset")
    inst = app.hub.state.get("installation") or {}
    return {"name": inst.get("name", ""), "instance_id": app.settings.instance, "version": __version__,
            "contract": CONTRACT, "auth": "token", "setup_required": not owners or bool(reset and reset.value),
            "hub": {"online": app.hub.online, "compatible": app.hub.compatible}}


class SetupIn(BaseModel):
    setup_code: str
    name: str = Field(min_length=1, max_length=80)
    timezone: str = "UTC"
    username: str
    password: str
    display_name: str = ""


@router.post("/setup", status_code=201)
async def setup(body: SetupIn, request: Request):
    app = app_of(request)
    code = await setup_code(app)
    if code is None:
        raise ApiError("already_set_up", "This gateway is already set up")
    import hmac
    if not hmac.compare_digest(code, body.setup_code.strip().upper()):
        raise ApiError("invalid_setup_code", "The setup code is wrong")
    username, _ = check_username(body.username), check_password(body.password)
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(body.timezone)
    except Exception:
        raise ApiError("validation", detail="timezone is not a known IANA zone")
    # the hub must take the installation settings first: without it the gateway is not usable
    await app.hub.request("installation_set", {"name": body.name, "timezone": body.timezone},
                          {"user_id": "setup", "role": "owner"})
    now = int(app.clock.now())
    async with app.sessions() as s:
        old = (await s.execute(select(User).where(User.role == "owner"))).scalar_one_or_none()
        if old is not None:                     # reset-owner: the former owner stays as an admin
            old.role = "admin"
            await s.flush()
        user = User(id=str(ULID()), username=username, password_hash=hash_password(body.password), role="owner",
                    display_name=body.display_name or username, created_at=now)
        s.add(user)
        for key in ("setup_code", "owner_reset"):
            row = await s.get(Setting, key)
            if row is not None:
                await s.delete(row)
        raw, tok = await new_session_token(app, s, user, "setup")
        await s.commit()
    await audit(app, user.id, "setup", {"name": body.name}, request)
    return {"token": raw, "token_id": tok.id, "user": user_view(user)}


# ---- login ------------------------------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str
    device_name: str = ""


@router.post("/auth/login")
async def login(body: LoginIn, request: Request):
    app = app_of(request)
    name = body.username.strip().lower()
    ip = request.client.host if request.client else "?"
    keys = [f"u:{name}", f"ip:{ip}"]
    for k in keys:
        app.check_login_allowed(k)
    async with app.sessions() as s:
        user = (await s.execute(select(User).where(User.username == name))).scalar_one_or_none()
        ok = verify_password(user.password_hash if user else None, body.password)
        if not ok or user.disabled_at is not None:
            for k in keys:
                app.login_failed(k)
            raise ApiError("invalid_credentials", "Wrong username or password")
        for k in keys:
            app.login_ok(k)
        raw, tok = await new_session_token(app, s, user, body.device_name)
        await s.commit()
    return {"token": raw, "token_id": tok.id, "user": user_view(user)}


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, p: Principal = Depends(current)):
    app = app_of(request)
    async with app.sessions() as s:
        await s.execute(update(Token).where(Token.id == p.token_id).values(revoked_at=int(app.clock.now())))
        await s.commit()
    app.events.close_token(p.token_id)


def token_view(t: Token, current_id: str) -> dict:
    return {"id": t.id, "name": t.name, "created_at": iso(t.created_at), "last_used_at": iso(t.last_used_at),
            "current": t.id == current_id}


@router.get("/auth/tokens")
async def list_tokens(request: Request, user_id: str | None = None, p: Principal = Depends(current)):
    app = app_of(request)
    target = p.user_id
    if user_id and user_id != p.user_id:
        if p.role not in ("admin", "owner"):
            raise ApiError("forbidden", "Only admins can see other users' tokens")
        target = user_id
    async with app.sessions() as s:
        rows = (await s.execute(select(Token).where(Token.user_id == target, Token.revoked_at.is_(None))
                                .order_by(Token.created_at))).scalars()
        return [token_view(t, p.token_id) for t in rows]


@router.delete("/auth/tokens/{token_id}", status_code=204)
async def revoke_token(token_id: str, request: Request, p: Principal = Depends(current)):
    app = app_of(request)
    async with app.sessions() as s:
        t = await s.get(Token, token_id)
        if t is None or (t.user_id != p.user_id and p.role not in ("admin", "owner")):
            raise ApiError("not_found", "Token not found")
        t.revoked_at = int(app.clock.now())
        await s.commit()
    app.events.close_token(token_id)


class ReauthIn(BaseModel):
    password: str


@router.post("/auth/reauth")
async def reauth(body: ReauthIn, request: Request, p: Principal = Depends(current)):
    app = app_of(request)
    app.check_login_allowed(f"u:{p.username}")
    async with app.sessions() as s:
        user = await s.get(User, p.user_id)
    if not verify_password(user.password_hash, body.password):
        app.login_failed(f"u:{p.username}")
        raise ApiError("invalid_credentials", "Wrong password")
    app.login_ok(f"u:{p.username}")
    proof = new_token()
    app.issue_proof(p.user_id, proof)
    return {"proof": proof, "expires_in": 300}


# ---- me ---------------------------------------------------------------------------------------------

@router.get("/me")
async def me(request: Request, p: Principal = Depends(current)):
    async with app_of(request).sessions() as s:
        return user_view(await s.get(User, p.user_id))


class MeIn(BaseModel):
    display_name: str | None = None
    password: str | None = None
    current_password: str | None = None


@router.patch("/me")
async def patch_me(body: MeIn, request: Request, p: Principal = Depends(current)):
    app = app_of(request)
    async with app.sessions() as s:
        u = await s.get(User, p.user_id)
        if body.display_name is not None:
            u.display_name = body.display_name.strip()[:80] or u.username
        if body.password is not None:
            if not verify_password(u.password_hash, body.current_password or ""):
                raise ApiError("invalid_credentials", "The current password is wrong")
            u.password_hash = hash_password(check_password(body.password))
            await s.execute(update(Token).where(Token.user_id == u.id, Token.id != p.token_id,
                                                Token.revoked_at.is_(None)).values(revoked_at=int(app.clock.now())))
        await s.commit()
        view = user_view(u)
    if body.password is not None:
        await audit(app, p.user_id, "password_changed", None, request)
    return view
