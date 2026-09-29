"""Live gateway WebSocket sessions of this process (Api_Specs §9.2)."""

import asyncio
from typing import Protocol


class Session(Protocol):
    gateway_id: str

    async def close(self, code: int, reason: str) -> None: ...


class GatewayRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._wakeups: dict[str, asyncio.Event] = {}

    async def register(self, session: Session) -> None:
        """One connection per gateway: a new one closes the old one (code 4000)."""
        old = self._sessions.get(session.gateway_id)
        self._sessions[session.gateway_id] = session
        if old is not None and old is not session:
            await old.close(4000, "replaced by a newer connection")

    def unregister(self, session: Session) -> None:
        if self._sessions.get(session.gateway_id) is session:
            del self._sessions[session.gateway_id]

    def is_connected(self, gateway_id: str) -> bool:
        return gateway_id in self._sessions

    async def close(self, gateway_id: str, code: int, reason: str) -> None:
        session = self._sessions.get(gateway_id)
        if session is not None:
            await session.close(code, reason)

    def wakeup(self, gateway_id: str) -> asyncio.Event:
        return self._wakeups.setdefault(gateway_id, asyncio.Event())

    def wake(self, gateway_id: str) -> None:
        """New downlink rows were committed for this gateway."""
        self.wakeup(gateway_id).set()
