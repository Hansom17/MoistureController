"""Application context and unit of work.

`AppContext` holds the long-lived objects (DB engine, key box, SSE bus, …).
`Uow` wraps one DB session: services add rows, queue messages for devices in
the outbox (v1; becomes the per-gateway downlink, Api_Specs §9.3) and record
live events; `commit()` makes it all happen atomically and only then notifies
SSE subscribers.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .config import Settings
from .crypto import KeyBox
from .db.models import Outbox
from .notify.push import PushSender
from .realtime.bus import EventBus


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    keys: KeyBox
    bus: EventBus
    push: PushSender
    outbox_wakeup: asyncio.Event = field(default_factory=asyncio.Event)

    @asynccontextmanager
    async def uow(self) -> AsyncIterator["Uow"]:
        async with self.sessionmaker() as session:
            yield Uow(self, session)


class Uow:
    def __init__(self, ctx: AppContext, session: AsyncSession):
        self.ctx = ctx
        self.s = session
        self._events: list[tuple[str, str, dict]] = []
        self._pushes: list[tuple[str, str, dict]] = []
        self._outbox = False

    # Recorded now, delivered after commit.

    def emit(self, household_id: str, kind: str, data: dict | None = None) -> None:
        self._events.append((household_id, kind, data or {}))

    def publish(self, topic: str, payload: dict | None, *, retain: bool = False, qos: int = 1):
        """Queue an MQTT publish in the outbox (None payload clears a retained topic)."""
        body = None if payload is None else json.dumps(payload, separators=(",", ":"))
        self.s.add(Outbox(topic=topic, payload=body, qos=qos, retain=retain))
        self._outbox = True

    def notify(self, household_id: str, title: str, data: dict) -> None:
        self._pushes.append((household_id, title, data))

    async def rollback(self) -> None:
        """Discard DB changes and everything recorded for after-commit."""
        await self.s.rollback()
        self._events.clear()
        self._pushes.clear()
        self._outbox = False

    async def commit(self) -> None:
        await self.s.commit()
        for household_id, kind, data in self._events:
            self.ctx.bus.publish(household_id, kind, data)
        if self._outbox:
            self.ctx.outbox_wakeup.set()
        pushes, self._pushes = self._pushes, []
        for household_id, title, data in pushes:
            asyncio.get_running_loop().create_task(
                self.ctx.push.send_to_household(self.ctx, household_id, title, data))
        self._events.clear()
        self._outbox = False
