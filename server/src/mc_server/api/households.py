from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from ..auth.deps import (
    Admin,
    CurrentUser,
    Owner,
    OwnerSensitive,
    UowDep,
    Viewer,
    require_recent_login,
)
from ..db.models import AuditLog, Membership, User
from ..services import households
from .schemas import (
    AuditOut,
    HouseholdCreate,
    HouseholdOut,
    HouseholdPatch,
    InviteCreate,
    InviteCreated,
    InviteOut,
    InvitePreview,
    MemberOut,
    MemberPatch,
    TransferIn,
)

router = APIRouter(tags=["households"])


async def _out(uow, household, role: str) -> HouseholdOut:
    from .me import gateway_summary

    return HouseholdOut(id=household.id, name=household.name, timezone=household.timezone,
                        battery_low_mv=household.battery_low_mv, role=role,
                        gateway=await gateway_summary(uow, household.id))


@router.post("/households", response_model=HouseholdOut, status_code=201)
async def create(body: HouseholdCreate, user: CurrentUser, uow: UowDep):
    household = await households.create(uow, user, body.name, body.timezone)
    return await _out(uow, household, "owner")


@router.get("/households/{household_id}", response_model=HouseholdOut)
async def get(h: Viewer):
    return await _out(h.uow, h.household, h.role)


@router.patch("/households/{household_id}", response_model=HouseholdOut)
async def patch(body: HouseholdPatch, h: Owner):
    household = await households.update(h.uow, h.household, h.user.uid, name=body.name,
                                        timezone=body.timezone,
                                        battery_low_mv=body.battery_low_mv)
    return await _out(h.uow, household, h.role)


@router.delete("/households/{household_id}", status_code=204)
async def delete(h: OwnerSensitive):
    await households.delete_household(h.uow, h.household, h.user.uid)
    return Response(status_code=204)


@router.post("/households/{household_id}/transfer-ownership", status_code=204)
async def transfer(body: TransferIn, h: OwnerSensitive):
    await households.transfer_ownership(h.uow, h.id, h.user, body.uid)
    return Response(status_code=204)


# --- members --------------------------------------------------------------------------


@router.get("/households/{household_id}/members", response_model=list[MemberOut])
async def members(h: Viewer):
    return [MemberOut(uid=u.uid, display_name=u.display_name, email=u.email, role=m.role,
                      joined_at=m.created_at)
            for m, u in await households.members(h.uow, h.id)]


@router.patch("/households/{household_id}/members/{uid}", response_model=MemberOut)
async def change_role(uid: str, body: MemberPatch, h: Admin, request: Request):
    target = await h.uow.s.get(Membership, (h.id, uid))
    if target is not None and "admin" in (target.role, body.role):
        await require_recent_login(request, h.user)  # admin changes are sensitive
    m = await households.change_role(h.uow, h.id, h.user, h.role, uid, body.role)
    user = await h.uow.s.get(User, uid)
    return MemberOut(uid=uid, display_name=user.display_name, email=user.email, role=m.role,
                     joined_at=m.created_at)


@router.delete("/households/{household_id}/members/{uid}", status_code=204)
async def remove_member(uid: str, h: Viewer):
    # Members may remove themselves; everything else is checked in the service.
    await households.remove_member(h.uow, h.id, h.user, h.role, uid)
    return Response(status_code=204)


# --- invites --------------------------------------------------------------------------


@router.get("/households/{household_id}/invites", response_model=list[InviteOut])
async def invites(h: Admin):
    return await households.list_invites(h.uow, h.id)


@router.post("/households/{household_id}/invites", response_model=InviteCreated,
             status_code=201)
async def create_invite(body: InviteCreate, h: Admin):
    invite, code = await households.create_invite(h.uow, h.id, h.user, h.role, body.role,
                                                  body.expires_in_h)
    return InviteCreated(id=invite.id, role=invite.role, created_at=invite.created_at,
                         expires_at=invite.expires_at, code=code,
                         url=f"{h.uow.ctx.settings.app_url}/join#c={code}")


@router.delete("/households/{household_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(invite_id: str, h: Admin):
    await households.revoke_invite(h.uow, h.id, invite_id, h.user.uid)
    return Response(status_code=204)


@router.get("/invites/{code}", response_model=InvitePreview)
async def preview_invite(code: str, user: CurrentUser, uow: UowDep):
    return await households.preview_invite(uow, code)


@router.post("/invites/{code}/accept", response_model=HouseholdOut)
async def accept_invite(code: str, user: CurrentUser, uow: UowDep):
    household = await households.accept_invite(uow, code, user)
    membership = await uow.s.get(Membership, (household.id, user.uid))
    return await _out(uow, household, membership.role)


@router.get("/households/{household_id}/audit", response_model=list[AuditOut])
async def audit_log(h: Admin, limit: int = 100):
    return list(await h.uow.s.scalars(select(AuditLog).where(
        AuditLog.household_id == h.id).order_by(AuditLog.ts.desc()).limit(min(limit, 500))))
