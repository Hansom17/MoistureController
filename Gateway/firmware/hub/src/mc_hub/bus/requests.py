"""Request handling (Gateway/specs.md 3.3): envelope check, deadline, idempotency, one at a time."""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mc_hub.clock import Clock
from mc_hub.db.models import RequestRecord
from mc_hub.errors import HubError

from .envelope import T_REQUEST, V, Actor, Request, dumps, err, ok
from .publisher import Publisher
from .transport import Transport

log = logging.getLogger("mc_hub.requests")
KEEP_S = 600


@dataclass
class Ctx:
    session: AsyncSession
    actor: Actor
    request_id: str
    now: int
    events: list[tuple[str, dict]] = field(default_factory=list)
    snapshots: set[str] = field(default_factory=set)

    def emit(self, kind: str, body: dict) -> None:
        self.events.append((kind, body))

    def touch(self, *names: str) -> None:
        self.snapshots.update(names)


HandlerFn = Callable[[Ctx, dict], Awaitable[dict | None]]


class RequestHandler:
    def __init__(self, transport: Transport, sessions: async_sessionmaker[AsyncSession],
                 publisher: Publisher, clock: Clock, publish_snapshots: Callable[[set[str]], Awaitable[None]],
                 lock: asyncio.Lock | None = None):
        self.t, self.sessions, self.pub, self.clock = transport, sessions, publisher, clock
        self.publish_snapshots = publish_snapshots
        self.handlers: dict[str, HandlerFn] = {}
        # Requests are processed one at a time: simple and ordered. One household is small.
        self._lock = lock or asyncio.Lock()

    def register(self, kind: str):
        def deco(fn: HandlerFn) -> HandlerFn:
            self.handlers[kind] = fn
            return fn
        return deco

    async def start(self) -> None:
        await self.t.subscribe(T_REQUEST + "#", self.on_message)

    async def on_message(self, topic: str, payload: bytes) -> None:
        kind = topic[len(T_REQUEST):]
        try:
            req = Request.model_validate(json.loads(payload))
        except (ValueError, ValidationError) as e:
            log.warning("dropping invalid request on %s: %s", topic, e)
            return
        if self.clock.dt() > req.deadline:
            log.info("ignoring expired request %s (%s)", req.id, kind)
            return
        async with self._lock:
            answer, ctx = await self._process(kind, req)
        await self.t.publish(req.reply_to, dumps(answer))
        if ctx is not None:
            for ekind, body in ctx.events:
                await self.pub.event(ekind, body)
            if ctx.snapshots:
                await self.publish_snapshots(ctx.snapshots)

    async def _process(self, kind: str, req: Request) -> tuple[dict, Ctx | None]:
        async with self.sessions() as s:
            stored = await s.get(RequestRecord, req.id)
            if stored is not None:
                return stored.answer, None  # repeated id: same answer, nothing executed
        if req.v != V:
            return self._store_error(kind, req, HubError("unsupported_version")), None
        fn = self.handlers.get(kind)
        if fn is None:
            return err(req.id, HubError("unknown_kind", detail=kind).as_dict()), None
        async with self.sessions() as s:
            ctx = Ctx(s, req.actor, req.id, int(self.clock.now()))
            try:
                body = await fn(ctx, req.body)
                answer = ok(req.id, body)
                s.add(RequestRecord(id=req.id, kind=kind, answer=answer, ts=ctx.now))
                await s.execute(delete(RequestRecord).where(RequestRecord.ts < ctx.now - KEEP_S))
                await s.commit()
                return answer, ctx
            except HubError as e:
                await s.rollback()
                return self._store_error(kind, req, e), None
            except Exception:
                await s.rollback()
                log.exception("request %s (%s) failed", req.id, kind)
                return err(req.id, {"type": "internal", "status": 500, "title": "internal error", "detail": ""}), None

    def _store_error(self, kind: str, req: Request, e: HubError) -> dict:
        # Not stored: errors are cheap to recompute and a retry may succeed after the cause is gone.
        return err(req.id, e.as_dict())
