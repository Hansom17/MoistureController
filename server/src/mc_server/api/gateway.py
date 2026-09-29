"""Gateway endpoints: app management, enrollment and the WebSocket (Api_Specs §9)."""

import asyncio
import logging
import time

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from mc_core.contract import gateway as g

from ..auth.deps import Admin, AdminSensitive, UowDep, Viewer
from ..context import AppContext
from ..db.models import CommandRow, Downlink, Gateway
from ..db.types import utcnow
from ..errors import not_found
from ..services import gateways
from ..services.common import audit
from .schemas import GatewayClaim, GatewayOut, GatewayPatch

log = logging.getLogger(__name__)

router = APIRouter(tags=["gateway"])
enroll_router = APIRouter(prefix="/gateway/v1/enroll", tags=["gateway enrollment"])
ws_router = APIRouter()

HELLO_TIMEOUT_S = 30
SENDER_POLL_S = 5


# --- app side ----------------------------------------------------------------------------


async def _gateway_or_404(h) -> Gateway:
    gw = await gateways.get_gateway(h.uow, h.id)
    if gw is None:
        raise not_found("gateway")
    return gw


@router.get("/households/{household_id}/gateway", response_model=GatewayOut)
async def get(h: Viewer):
    return gateways.view(h.uow, await _gateway_or_404(h), h.household)


@router.post("/households/{household_id}/gateway", response_model=GatewayOut, status_code=201)
async def claim(body: GatewayClaim, h: AdminSensitive):
    gw = await gateways.claim(h.uow, h.household, body.user_code, h.user.uid)
    return gateways.view(h.uow, gw, h.household)


@router.patch("/households/{household_id}/gateway", response_model=GatewayOut)
async def patch(body: GatewayPatch, h: Admin):
    gw = await _gateway_or_404(h)
    gw.lan_host_override = body.lan_host_override or None
    audit(h.uow, h.id, h.user.uid, "gateway.lan_host", {"lan_host_override": gw.lan_host_override})
    h.uow.emit(h.id, "gateway", {})
    await h.uow.commit()
    return gateways.view(h.uow, gw, h.household)


@router.delete("/households/{household_id}/gateway", status_code=204)
async def remove(h: AdminSensitive):
    await gateways.remove(h.uow, h.id, h.user.uid)
    return Response(status_code=204)


# --- enrollment: no user auth (gateway_api.md §3) ----------------------------------------


@enroll_router.post("/start", response_model=g.EnrollStartResponse, status_code=201)
async def start(body: g.EnrollStartRequest, request: Request, uow: UowDep):
    ip = request.client.host if request.client else None
    return await gateways.enroll_start(uow, body, ip)


@enroll_router.post("/poll", response_model=g.EnrollPollResponse,
                    responses={202: {"description": "pending"}, 410: {"description": "gone"}})
async def poll(body: g.EnrollPollRequest, uow: UowDep):
    result = await gateways.enroll_poll(uow, body.enroll_id, body.secret)
    if result is None:
        return Response('{"status":"pending"}', status_code=202, media_type="application/json")
    return result


# --- WebSocket (gateway_api.md §4) -------------------------------------------------------------


@ws_router.websocket("/gateway/v1/connect")
async def connect(ws: WebSocket):
    ctx: AppContext = ws.app.state.ctx
    async with ctx.uow() as uow:
        gw = await gateways.authenticate(uow, ws.headers.get("authorization", ""))
        ident = None if gw is None else (gw.id, gw.household_id)
    if ident is None:
        await ws.close(code=1008)  # before accept → HTTP 403
        return
    await ws.accept()
    await GatewaySession(ctx, ws, *ident).run()


class GatewaySession:
    def __init__(self, ctx: AppContext, ws: WebSocket, gateway_id: str, household_id: str):
        self.ctx = ctx
        self.ws = ws
        self.gateway_id = gateway_id
        self.household_id = household_id
        self._send_lock = asyncio.Lock()
        self._stopping = False

    async def close(self, code: int, reason: str) -> None:
        try:
            await self.ws.close(code=code, reason=reason)
        except RuntimeError:
            pass  # already closed

    async def send(self, message: dict) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        await self.ctx.gateways.register(self)
        sender: asyncio.Task | None = None
        try:
            first = await asyncio.wait_for(self.ws.receive_json(), HELLO_TIMEOUT_S)
            hello = g.Hello.model_validate(first)
            async with self.ctx.uow() as uow:
                gw = await uow.s.get(Gateway, self.gateway_id)
                await gateways.connected(uow, gw, hello)
                ack_seq = gw.last_up_seq
            await self.send({"t": "welcome", "ack_seq": ack_seq, "server_time": int(time.time())})
            log.info("gateway %s connected (ack_seq %s)", self.gateway_id, ack_seq)
            sender = asyncio.create_task(self._sender())
            while True:
                await self._receive(await self.ws.receive_json())
        except (WebSocketDisconnect, TimeoutError, RuntimeError):
            pass
        except ValueError as e:  # not JSON, or not a hello
            log.warning("gateway %s: protocol error: %s", self.gateway_id, str(e)[:200])
            await self.close(1002, "protocol error")
        finally:
            if sender is not None:
                await self._stop(sender)
            self.ctx.gateways.unregister(self)
            if not self.ctx.gateways.is_connected(self.gateway_id):
                async with self.ctx.uow() as uow:
                    await gateways.disconnected(uow, self.gateway_id)
            log.info("gateway %s disconnected", self.gateway_id)

    async def _receive(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "down_ack":
            try:
                ack = g.DownAck.model_validate(msg)
            except ValidationError as e:
                log.warning("gateway %s: invalid down_ack: %s", self.gateway_id, str(e)[:200])
                return
            async with self.ctx.uow() as uow:
                gw = await uow.s.get(Gateway, self.gateway_id)
                await gateways.process_down_ack(uow, gw, ack)
            return
        if t == "hello":
            return  # only valid as the first message
        seq = msg.get("seq")
        if not isinstance(seq, int):
            log.info("gateway %s: message without seq (%r) ignored", self.gateway_id, t)
            return
        async with self.ctx.uow() as uow:
            gw = await uow.s.get(Gateway, self.gateway_id)
            if seq > gw.last_up_seq:  # else: replay of something already stored
                await gateways.process_up(uow, gw, msg)
            acked = (await uow.s.get(Gateway, self.gateway_id)).last_up_seq
        await self.send({"t": "ack", "seq": acked})

    async def _stop(self, sender: asyncio.Task) -> None:
        """Lets the sender finish its current DB round: cancelling it mid-query
        would hand a broken connection back to the pool."""
        self._stopping = True
        self.ctx.gateways.wake(self.gateway_id)
        try:
            await asyncio.wait_for(sender, 10)
        except Exception:  # noqa: BLE001 — socket already gone, or it timed out
            pass

    async def _sender(self) -> None:
        """Sends unacknowledged downlink rows in order (Api_Specs §9.3)."""
        sent: set[str] = set()
        wakeup = self.ctx.gateways.wakeup(self.gateway_id)
        while not self._stopping:
            wakeup.clear()
            removed = False
            async with self.ctx.uow() as uow:
                rows = (await uow.s.scalars(select(Downlink).where(
                    Downlink.gateway_id == self.gateway_id, Downlink.acked_at.is_(None))
                    .order_by(Downlink.created_at, Downlink.id))).all()
                for row in rows:
                    if row.id in sent:
                        continue
                    if row.type == "command" and not await self._still_open(uow, row):
                        row.acked_at, row.result = utcnow(), "superseded"
                        continue
                    await self.send(row.body)
                    row.sent_at = utcnow()
                    sent.add(row.id)
                    if row.type == "removed":
                        row.acked_at, row.result = utcnow(), "applied"  # no ack will follow
                        removed = True
                await uow.commit()
            if removed:
                await self.close(4001, "gateway removed")
                return
            try:
                await asyncio.wait_for(wakeup.wait(), SENDER_POLL_S)
            except TimeoutError:
                pass

    @staticmethod
    async def _still_open(uow, row: Downlink) -> bool:
        cmd = await uow.s.get(CommandRow, row.body["command"]["id"])
        return cmd is not None and cmd.status in ("queued", "cancelling")
