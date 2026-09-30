"""FastAPI dependencies: current user, household role, recent login (§5)."""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from ..context import AppContext, Uow
from ..db.models import ROLES, Household, Membership, User
from ..errors import Problem, not_found
from .verify import Principal

RECENT_LOGIN_S = 5 * 60


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_uow(ctx: Annotated[AppContext, Depends(get_ctx)]) -> AsyncIterator[Uow]:
    async with ctx.uow() as uow:
        yield uow


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Problem(401, "missing_token")
    return token


async def get_principal(request: Request, uow: Annotated[Uow, Depends(get_uow)]) -> Principal:
    principal = await request.app.state.verifier.verify(_bearer(request))
    user = await uow.s.get(User, principal.uid)
    if user is None:
        uow.s.add(User(uid=principal.uid,
                       email=principal.email if principal.email_verified else None,
                       display_name=principal.name))
        await uow.s.commit()
    elif principal.email_verified and user.email != principal.email:
        user.email = principal.email
        await uow.s.commit()
    return principal


CurrentUser = Annotated[Principal, Depends(get_principal)]
UowDep = Annotated[Uow, Depends(get_uow)]


def require_verified(principal: Principal) -> None:
    if not principal.email_verified:
        raise Problem(403, "email_not_verified")


async def require_recent_login(request: Request, principal: Principal) -> None:
    """Sensitive actions (§5.3): sign-in ≤ 5 min ago + revocation check."""
    if time.time() - principal.auth_time > RECENT_LOGIN_S:
        raise Problem(401, "reauth_required")
    await request.app.state.verifier.verify(_bearer(request), check_revoked=True)


@dataclass
class HouseholdCtx:
    household: Household
    role: str
    user: Principal
    uow: Uow

    @property
    def id(self) -> str:
        return self.household.id

    def at_least(self, role: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(role)


def require_role(min_role: str, *, sensitive: bool = False):
    """Not a member → 404, role too low → 403 (§5.2)."""

    async def dep(household_id: str, request: Request, user: CurrentUser,
                  uow: UowDep) -> HouseholdCtx:
        row = (await uow.s.execute(
            select(Household, Membership.role)
            .join(Membership, Membership.household_id == Household.id)
            .where(Household.id == household_id, Membership.user_uid == user.uid)
        )).first()
        if row is None:
            raise not_found("household")
        household, role = row
        if ROLES.index(role) < ROLES.index(min_role):
            raise Problem(403, "forbidden", f"requires {min_role}")
        if sensitive:
            await require_recent_login(request, user)
        return HouseholdCtx(household, role, user, uow)

    return dep


def Role(min_role: str, *, sensitive: bool = False):  # noqa: N802 — reads like a type
    return Annotated[HouseholdCtx, Depends(require_role(min_role, sensitive=sensitive))]


Viewer = Role("viewer")
Member = Role("member")
Admin = Role("admin")
Owner = Role("owner")
AdminSensitive = Role("admin", sensitive=True)
OwnerSensitive = Role("owner", sensitive=True)
