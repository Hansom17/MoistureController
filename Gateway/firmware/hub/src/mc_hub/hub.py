"""Wires transport, database, request handler, ingest and snapshots into one service."""
import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bus.publisher import Publisher
from .bus.requests import RequestHandler
from .bus.transport import Transport
from .clock import Clock
from .services import domain
from .services.effects import Effects
from .services.ingest import Ingest
from .services.snapshots import NAMES, Snapshots
from .zigbee.topics import Z2MTopics, parse_state_value

log = logging.getLogger("mc_hub")


class Hub:
    def __init__(self, transport: Transport, sessions: async_sessionmaker[AsyncSession], clock: Clock,
                 publisher: Publisher, z2m_base: str = "zigbee2mqtt") -> None:
        self.t, self.sessions, self.clock, self.pub = transport, sessions, clock, publisher
        self.topics = Z2MTopics(z2m_base)
        self.lock = asyncio.Lock()
        self.snapshots = Snapshots(sessions, publisher)
        self.ingest = Ingest(sessions, transport, self.topics, clock)
        self.requests = RequestHandler(transport, sessions, publisher, clock, self.snapshots.publish, self.lock)
        domain.register(self.requests)

    async def start(self) -> None:
        await self.snapshots.publish(NAMES)
        await self.pub.status("online")
        await self.requests.start()
        await self.t.subscribe(self.topics.bridge_state, self._on_bridge_state)
        await self.t.subscribe(self.topics.bridge_devices, self._on_bridge_devices)
        await self.t.subscribe(self.topics.device_state, self._on_device)
        await self.t.subscribe(self.topics.device_availability, self._on_device)

    async def stop(self) -> None:
        await self.pub.status("offline")

    async def _flush(self, fx: Effects) -> None:
        for kind, body in fx.events:
            await self.pub.event(kind, body)
        if fx.snapshots:
            await self.snapshots.publish(fx.snapshots)

    async def _on_bridge_state(self, topic: str, payload: bytes) -> None:
        state = parse_state_value(payload)
        self.snapshots.extra_status["zigbee2mqtt"] = state
        await self.snapshots.publish({"status"})

    async def _on_bridge_devices(self, topic: str, payload: bytes) -> None:
        try:
            devices = json.loads(payload)
        except ValueError:
            log.warning("bad bridge/devices payload")
            return
        async with self.lock:
            fx = await self.ingest.reconcile(devices)
        await self._flush(fx)

    async def _on_device(self, topic: str, payload: bytes) -> None:
        parsed = self.topics.parse(topic)
        if parsed is None:
            return
        kind, name = parsed
        # friendly names equal the internal device ids once the rename has happened
        dev_id = name
        try:
            async with self.lock:
                if kind == "availability":
                    fx = await self.ingest.availability(dev_id, parse_state_value(payload))
                else:
                    data = json.loads(payload)
                    if not isinstance(data, dict):
                        return
                    fx = await self.ingest.state(dev_id, data)
        except ValueError:
            log.warning("bad payload on %s", topic)
            return
        await self._flush(fx)
