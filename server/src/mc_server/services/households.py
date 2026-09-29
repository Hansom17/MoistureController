"""Households, members, invites (Server_Specs §5.2, §6.1)."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select

from ..auth.verify import Principal
from ..context import Uow
from ..db.models import ROLES, Household, Invite, Membership, User
from ..db.types import utcnow
from ..errors import Problem, not_found
from . import hubs
from .common import audit

INVITE_MAX_H = 24 * 14


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


async def list_for_user(uow: Uow, uid: str) -> list[tuple[Household, str]]:
    rows = await uow.s.execute(
        select(Household, Membership.role)
        .join(Membership, Membership.household_id == Household.id)
        .where(Membership.user_uid == uid).order_by(Household.created_at))
    return [(h, r) for h, r in rows]


async def create(uow: Uow, user: Principal, name: str, timezone: str) -> Household:
    if not user.email_verified:
        raise Problem(403, "email_not_verified")
    count = await uow.s.scalar(select(func.count()).where(
        Membership.user_uid == user.uid, Membership.role == "owner"))
    if count >= uow.ctx.settings.max_households_per_user:
        raise Problem(409, "quota_exceeded")
    _check_tz(timezone)
    household = Household(name=name, timezone=timezone)
    uow.s.add(household)
    await uow.s.flush()
    uow.s.add(Membership(household_id=household.id, user_uid=user.uid, role="owner"))
    audit(uow, household.id, user.uid, "household.create", {"name": name})
    await uow.commit()
    return household


def _check_tz(tz: str) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise Problem(422, "invalid_timezone") from e


async def update(uow: Uow, household: Household, uid: str, *, name: str | None,
                 timezone: str | None, battery_low_mv: int | None) -> Household:
    if name is not None:
        household.name = name
    if timezone is not None:
        _check_tz(timezone)
        household.timezone = timezone
    if battery_low_mv is not None:
        household.battery_low_mv = battery_low_mv
    if timezone is not None or battery_low_mv is not None:
        await hubs.republish_snapshot(uow, household.id)
    audit(uow, household.id, uid, "household.update")
    uow.emit(household.id, "household", {})
    await uow.commit()
    return household


async def delete_household(uow: Uow, household: Household, uid: str) -> None:
    from mc_core.contract import topics

    from ..db.models import Device
    from .common import get_hub

    if await get_hub(uow, household.id) is not None:
        await hubs.remove(uow, household.id, uid)
    for d in await uow.s.scalars(select(Device).where(Device.household_id == household.id)):
        for suffix in ("status", "config/desired", "config/state"):
            uow.publish(topics.device(d.id, suffix), None, retain=True)
    uow.broker_files_changed()
    audit(uow, None, uid, "household.delete", {"household_id": household.id})
    uow.emit(household.id, "household", {"deleted": True})
    await uow.s.delete(household)
    await uow.commit()


# --- members -----------------------------------------------------------------------


async def members(uow: Uow, household_id: str) -> list[tuple[Membership, User]]:
    rows = await uow.s.execute(
        select(Membership, User).join(User, User.uid == Membership.user_uid)
        .where(Membership.household_id == household_id).order_by(Membership.created_at))
    return [(m, u) for m, u in rows]


async def _membership(uow: Uow, household_id: str, uid: str) -> Membership:
    m = await uow.s.get(Membership, (household_id, uid))
    if m is None:
        raise not_found("member")
    return m


def _may_manage(actor_role: str, target_role: str, new_role: str | None = None) -> bool:
    """Owner manages everyone but itself; admins manage members/viewers up to member."""
    if actor_role == "owner":
        return target_role != "owner" and new_role != "owner"
    if actor_role == "admin":
        return target_role in ("member", "viewer") and new_role in (None, "member", "viewer")
    return False


async def change_role(uow: Uow, household_id: str, actor: Principal, actor_role: str,
                      uid: str, role: str) -> Membership:
    if role not in ROLES:
        raise Problem(422, "invalid_role")
    m = await _membership(uow, household_id, uid)
    if not _may_manage(actor_role, m.role, role):
        raise Problem(403, "forbidden")
    old, m.role = m.role, role
    audit(uow, household_id, actor.uid, "member.role", {"uid": uid, "from": old, "to": role})
    uow.emit(household_id, "household", {"members": True})
    await uow.commit()
    return m


async def remove_member(uow: Uow, household_id: str, actor: Principal, actor_role: str,
                        uid: str) -> None:
    m = await _membership(uow, household_id, uid)
    if m.role == "owner":
        raise Problem(409, "owner_cannot_leave", "transfer ownership first")
    if uid != actor.uid and not _may_manage(actor_role, m.role):
        raise Problem(403, "forbidden")
    await uow.s.delete(m)
    audit(uow, household_id, actor.uid, "member.remove", {"uid": uid})
    uow.emit(household_id, "household", {"members": True})
    await uow.commit()
    uow.ctx.bus.close_user(household_id, uid)


async def transfer_ownership(uow: Uow, household_id: str, actor: Principal, uid: str) -> None:
    new_owner = await _membership(uow, household_id, uid)
    old_owner = await _membership(uow, household_id, actor.uid)
    old_owner.role = "admin"
    await uow.s.flush()  # the one-owner index must never see two owners
    new_owner.role = "owner"
    audit(uow, household_id, actor.uid, "household.transfer", {"to": uid})
    uow.emit(household_id, "household", {"members": True})
    await uow.commit()


# --- invites -----------------------------------------------------------------------


async def create_invite(uow: Uow, household_id: str, actor: Principal, actor_role: str,
                        role: str, expires_in_h: int) -> tuple[Invite, str]:
    if role not in ("admin", "member", "viewer"):
        raise Problem(422, "invalid_role")
    if role == "admin" and actor_role != "owner":
        raise Problem(403, "forbidden", "only the owner invites admins")
    if not 1 <= expires_in_h <= INVITE_MAX_H:
        raise Problem(422, "out_of_range", f"expires_in_h 1–{INVITE_MAX_H}")
    since = utcnow() - timedelta(days=1)
    today = await uow.s.scalar(select(func.count()).where(
        Invite.household_id == household_id, Invite.created_at >= since))
    if today >= 20:
        raise Problem(429, "rate_limited")
    code = secrets.token_urlsafe(18)
    invite = Invite(household_id=household_id, code_hash=_hash(code), role=role,
                    created_by=actor.uid, expires_at=utcnow() + timedelta(hours=expires_in_h))
    uow.s.add(invite)
    audit(uow, household_id, actor.uid, "invite.create", {"role": role})
    await uow.commit()
    return invite, code


async def list_invites(uow: Uow, household_id: str) -> list[Invite]:
    return list(await uow.s.scalars(select(Invite).where(
        Invite.household_id == household_id, Invite.used_at.is_(None),
        Invite.revoked_at.is_(None), Invite.expires_at > utcnow())))


async def revoke_invite(uow: Uow, household_id: str, invite_id: str, uid: str) -> None:
    invite = await uow.s.scalar(select(Invite).where(
        Invite.id == invite_id, Invite.household_id == household_id))
    if invite is None:
        raise not_found("invite")
    invite.revoked_at = utcnow()
    audit(uow, household_id, uid, "invite.revoke", {"invite_id": invite_id})
    await uow.commit()


async def _valid_invite(uow: Uow, code: str) -> Invite:
    invite = await uow.s.scalar(select(Invite).where(Invite.code_hash == _hash(code)))
    if (invite is None or invite.used_at or invite.revoked_at
            or invite.expires_at < utcnow()):
        raise Problem(410, "invite_invalid")
    return invite


async def preview_invite(uow: Uow, code: str) -> dict:
    invite = await _valid_invite(uow, code)
    household = await uow.s.get(Household, invite.household_id)
    inviter = await uow.s.get(User, invite.created_by)
    return {"household_name": household.name, "role": invite.role,
            "invited_by": inviter.display_name if inviter else None,
            "expires_at": invite.expires_at}


async def accept_invite(uow: Uow, code: str, user: Principal) -> Household:
    if not user.email_verified:
        raise Problem(403, "email_not_verified")
    invite = await _valid_invite(uow, code)
    if await uow.s.get(Membership, (invite.household_id, user.uid)) is not None:
        raise Problem(409, "already_member")
    invite.used_by, invite.used_at = user.uid, utcnow()
    uow.s.add(Membership(household_id=invite.household_id, user_uid=user.uid, role=invite.role))
    audit(uow, invite.household_id, user.uid, "invite.accept", {"role": invite.role})
    uow.emit(invite.household_id, "household", {"members": True})
    await uow.commit()
    return await uow.s.get(Household, invite.household_id)


# --- account -----------------------------------------------------------------------


async def delete_account(uow: Uow, user: Principal) -> None:
    """`DELETE /me` (§6.1): leave everything; refuse while sole owner of a shared household."""
    for household, role in await list_for_user(uow, user.uid):
        if role != "owner":
            continue
        others = await uow.s.scalar(select(func.count()).where(
            Membership.household_id == household.id, Membership.user_uid != user.uid))
        if others:
            raise Problem(409, "sole_owner", household.name)
    for household, role in await list_for_user(uow, user.uid):
        if role == "owner":
            await delete_household(uow, household, user.uid)
    await uow.s.execute(delete(Membership).where(Membership.user_uid == user.uid))
    user_row = await uow.s.get(User, user.uid)
    if user_row is not None:
        await uow.s.delete(user_row)
    await uow.commit()
