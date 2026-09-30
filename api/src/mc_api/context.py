"""Application context and unit of work.

`AppContext` holds the long-lived objects (DB engine, key box, SSE bus,
gateway sessions). `Uow` wraps one DB session: services add rows, queue
messages for a gateway in the downlink table and record live events;
`commit()` makes it all happen atomically and only then notifies SSE
subscribers and the gateway senders (Api_Specs §3, §9.3).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from mc_core.ids import new_id

from .config import Settings
from .crypto import KeyBox
from .db.models import Downlink
from .notify.push import PushSender
from .realtime.bus import EventBus
from .realtime.gateways import GatewayRegistry


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    keys: KeyBox
    bus: EventBus
    push: PushSender
    gateways: GatewayRegistry = field(default_factory=GatewayRegistry)

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
        self._woken: set[str] = set()

    # Recorded now, delivered after commit.

    def emit(self, household_id: str, kind: str, data: dict | None = None) -> None:
        self._events.append((household_id, kind, data or {}))

    def send_down(self, gateway_id: str, type_: str, body: dict) -> Downlink:
        """Queue a down message (gateway_api.md §6) for the gateway."""
        msg_id = new_id()
        row = Downlink(id=msg_id, gateway_id=gateway_id, type=type_,
                       body={"t": type_, "id": msg_id, **body})
        self.s.add(row)
        self._woken.add(gateway_id)
        return row

    def notify(self, household_id: str, title: str, data: dict) -> None:
        self._pushes.append((household_id, title, data))

    async def rollback(self) -> None:
        """Discard DB changes and everything recorded for after-commit."""
        await self.s.rollback()
        self._events.clear()
        self._pushes.clear()
        self._woken.clear()

    async def commit(self) -> None:
        await self.s.commit()
        for household_id, kind, data in self._events:
            self.ctx.bus.publish(household_id, kind, data)
        for gateway_id in self._woken:
            self.ctx.gateways.wake(gateway_id)
        pushes, self._pushes = self._pushes, []
        for household_id, title, data in pushes:
            asyncio.get_running_loop().create_task(
                self.ctx.push.send_to_household(self.ctx, household_id, title, data))
        self._events.clear()
        self._woken.clear()
