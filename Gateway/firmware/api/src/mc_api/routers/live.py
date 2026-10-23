"""Server-sent events (Gateway/specs.md 6.1)."""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from mc_api.auth import Principal, app_of, require
from mc_api.convert import to_api
from mc_api.db.models import Token, User
from mc_api.errors import ApiError
from mc_api.realtime.bus import CLOSE

router = APIRouter()
PING_S = 25


@router.post("/events/ticket")
async def ticket(request: Request, p: Principal = Depends(require("viewer"))):
    return {"ticket": app_of(request).events.issue_ticket(p.user_id, p.token_id), "expires_in": 60}


def frame(id: int | None, kind: str, data: dict) -> str:
    head = f"id: {id}\n" if id is not None else ""
    return f"{head}event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/stream")
async def stream(request: Request, ticket: str):
    app = app_of(request)
    who = app.events.redeem_ticket(ticket)
    if who is None:
        raise ApiError("unauthorized", "The stream ticket is invalid or expired")
    user_id, token_id = who
    last = request.headers.get("last-event-id")
    sub = app.events.subscribe(user_id, token_id, int(last) if last and last.isdigit() else None)
    ping = float(request.app.state.ping_s)

    async def gen():
        try:
            yield frame(None, "hello", {"hub": app.hub.online})
            while True:
                try:
                    ev = await asyncio.wait_for(sub.queue.get(), ping)
                except asyncio.TimeoutError:
                    async with app.sessions() as s:        # a revoked token ends its stream
                        row = await s.get(Token, token_id)
                        user = await s.get(User, user_id)
                    if row is None or row.revoked_at or user is None or user.disabled_at:
                        return
                    yield frame(None, "ping", {})
                    continue
                if ev is CLOSE:
                    return
                yield frame(ev.id, ev.kind, ev.data)
        finally:
            app.events.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
