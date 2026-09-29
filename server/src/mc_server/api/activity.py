"""Commands, alerts and the live stream."""

import asyncio
import json

from fastapi import APIRouter, Header, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from ..auth.deps import Member, UowDep, Viewer
from ..db.models import Alert, CommandRow, Membership
from ..errors import Problem, not_found
from ..realtime.bus import CLOSE
from ..services import alerts, commands
from .schemas import AlertOut, CommandOut

router = APIRouter(prefix="/households/{household_id}", tags=["activity"])

PING_S = 25


@router.get("/commands", response_model=list[CommandOut])
async def list_commands(h: Viewer, status: str | None = None, device_id: str | None = None,
                        plant_id: str | None = None, origin: str | None = None,
                        limit: int = 50):
    q = select(CommandRow).where(CommandRow.household_id == h.id)
    if status:
        q = q.where(CommandRow.status == status)
    if device_id:
        q = q.where(CommandRow.device_id == device_id)
    if plant_id:
        q = q.where(CommandRow.plant_id == plant_id)
    if origin:
        q = q.where(CommandRow.origin == origin)
    rows = await h.uow.s.scalars(q.order_by(CommandRow.created_at.desc()).limit(min(limit, 500)))
    return [commands.view(c) for c in rows]


@router.get("/commands/{command_id}", response_model=CommandOut)
async def get_command(command_id: str, h: Viewer):
    return commands.view(await commands.get_command(h.uow, h.id, command_id))


@router.post("/commands/{command_id}/cancel", response_model=CommandOut, status_code=202)
async def cancel(command_id: str, h: Member):
    return commands.view(await commands.cancel(h.uow, h.id, command_id, h.user.uid))


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(h: Viewer, open_only: bool = False, limit: int = 100):
    q = select(Alert).where(Alert.household_id == h.id)
    if open_only:
        q = q.where(Alert.resolved_at.is_(None))
    return list(await h.uow.s.scalars(q.order_by(Alert.opened_at.desc()).limit(min(limit, 500))))


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def ack(alert_id: str, h: Member):
    return await alerts.acknowledge(h.uow, h.id, alert_id, h.user.uid)


@router.get("/stream", response_class=EventSourceResponse,
            responses={200: {"content": {"text/event-stream": {}}}})
async def stream(household_id: str, ticket: str, request: Request, uow: UowDep,
                 last_event_id: str | None = Header(None)):
    """SSE (§6.2). Authenticated by a single-use ticket from `POST /events/ticket`."""
    uid = uow.ctx.bus.redeem_ticket(ticket)
    if uid is None:
        raise Problem(401, "invalid_ticket")
    if await uow.s.get(Membership, (household_id, uid)) is None:
        raise not_found("household")
    await uow.s.close()  # don't hold a DB connection for the stream's lifetime
    bus = uow.ctx.bus
    try:
        last = int(last_event_id) if last_event_id else None
    except ValueError:
        last = None
    sub = bus.subscribe(household_id, uid, last)

    async def events():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), PING_S)
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if event is CLOSE or await request.is_disconnected():
                    return
                yield {"id": str(event.id), "event": event.kind, "data": json.dumps(event.data)}
        finally:
            bus.unsubscribe(household_id, sub)

    return EventSourceResponse(events())
