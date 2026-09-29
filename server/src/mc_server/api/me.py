from fastapi import APIRouter, Response

from mc_core import pins

from ..auth.deps import CurrentUser, UowDep
from ..db.models import PushToken, User
from ..errors import not_found
from ..realtime.bus import TICKET_TTL_S
from ..services import households
from .schemas import HouseholdOut, MeOut, PushTokenIn, TicketOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, uow: UowDep):
    row = await uow.s.get(User, user.uid)
    return MeOut(uid=user.uid, email=user.email, email_verified=user.email_verified,
                 display_name=row.display_name if row else user.name)


@router.delete("/me", status_code=204)
async def delete_me(user: CurrentUser, uow: UowDep):
    await households.delete_account(uow, user)
    return Response(status_code=204)


@router.get("/me/households", response_model=list[HouseholdOut])
async def my_households(user: CurrentUser, uow: UowDep):
    out = []
    for h, role in await households.list_for_user(uow, user.uid):
        out.append(HouseholdOut(id=h.id, name=h.name, timezone=h.timezone,
                                battery_low_mv=h.battery_low_mv, role=role))
    return out


@router.put("/me/push-tokens/{token}", status_code=204)
async def put_push_token(token: str, body: PushTokenIn, user: CurrentUser, uow: UowDep):
    row = await uow.s.get(PushToken, token)
    if row is None:
        uow.s.add(PushToken(token=token, user_uid=user.uid, platform=body.platform))
    else:
        row.user_uid, row.platform = user.uid, body.platform
    await uow.commit()
    return Response(status_code=204)


@router.delete("/me/push-tokens/{token}", status_code=204)
async def delete_push_token(token: str, user: CurrentUser, uow: UowDep):
    row = await uow.s.get(PushToken, token)
    if row is not None and row.user_uid == user.uid:
        await uow.s.delete(row)
        await uow.commit()
    return Response(status_code=204)


@router.post("/events/ticket", response_model=TicketOut)
async def ticket(user: CurrentUser, uow: UowDep):
    return TicketOut(ticket=uow.ctx.bus.issue_ticket(user.uid), expires_in=TICKET_TTL_S)


@router.get("/meta/boards/{board}")
async def board(board: str) -> dict:
    if board != pins.BOARD:
        raise not_found("board")
    return pins.board_description()
