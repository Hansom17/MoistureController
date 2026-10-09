"""Wires transport, database, request handler, ingest and snapshots into one service."""
import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bus.publisher import Publisher
from .bus.requests import RequestHandler
from .bus.transport import Transport
from .clock import Clock
from .services import domain, handlers, queries
from .services.backup import Backup
from .services.join import Join
from .services.jobs import Jobs
from .services.notify import Notifier, Send, telegram_send
from .services.sender import Sender
from .services.effects import Effects
from .services.ingest import Ingest
from .services.snapshots import NAMES, Snapshots
from .zigbee.topics import Z2MTopics, parse_state_value

log = logging.getLogger("mc_hub")


class Hub:
    def __init__(self, transport: Transport, sessions: async_sessionmaker[AsyncSession], clock: Clock,
                 publisher: Publisher, z2m_base: str = "zigbee2mqtt", telegram: Send = telegram_send,
                 engine=None, backup_dir=None) -> None:
        self.t, self.sessions, self.clock, self.pub = transport, sessions, clock, publisher
        self.topics = Z2MTopics(z2m_base)
        self.lock = asyncio.Lock()
        self.snapshots = Snapshots(sessions, publisher)
        self.ingest = Ingest(sessions, transport, self.topics, clock)
        self.sender = Sender(sessions, transport, self.topics, clock)
        self.join = self.ingest.join
        self.snapshots.join = self.join.state
        self.backup = Backup(engine, backup_dir) if engine is not None and backup_dir is not None else None
        self.jobs = Jobs(sessions, clock, self.topics, self.join, self.backup)
        self.notifier = Notifier(sessions, telegram)
        self.requests = RequestHandler(transport, sessions, publisher, clock, self._flush, self._publish_state, self.lock)
        domain.register(self.requests)
        handlers.register(self.requests, self)
        queries.register(self.requests, self.snapshots)

    async def start(self) -> None:
        await self.snapshots.publish(NAMES)
        await self.pub.status("online")
        await self.requests.start()
        await self.t.subscribe(self.topics.bridge_state, self._on_bridge_state)
        await self.t.subscribe(self.topics.bridge_devices, self._on_bridge_devices)
        await self.t.subscribe(self.topics.bridge_response_permit_join, self._on_permit_join)
        await self.t.subscribe(self.topics.device_state, self._on_device)
        await self.t.subscribe(self.topics.device_availability, self._on_device)

    async def stop(self) -> None:
        await self.pub.status("offline")

    async def _publish_state(self, fx: Effects) -> None:
        """Events and snapshots of a committed change (published once)."""
        events, snaps = fx.events, fx.snapshots
        fx.events, fx.snapshots = [], set()
        for kind, body in events:
            await self.pub.event(kind, body)
        if snaps:
            await self.snapshots.publish(snaps)

    async def _flush(self, fx: Effects) -> None:
        """Publish what a committed change produced, then let the sender look at the touched devices."""
        await self._publish_state(fx)
        for note in await self.notifier.deliver(fx.notes):
            await self.pub.event("notification", note)
        for topic, payload in fx.out:
            await self.t.publish(topic, payload)
        for did in fx.returned:
            async with self.lock:
                await self.sender.device_returned(did)
        for did in fx.wake:
            async with self.lock:
                more = await self.sender.flush(did)
            for kind, body in more.events:
                await self.pub.event(kind, body)

    async def _on_permit_join(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except ValueError:
            return
        if data.get("status") == "error" and self.join.state["open"]:
            async with self.lock:
                self.join.close(error=str(data.get("error", "permit_join failed")))
            await self.pub.event("join", dict(self.join.state))
            await self.snapshots.publish({"join"})

    async def tick(self) -> None:
        """One round of the periodic jobs (the service calls this every second)."""
        async with self.lock:
            fx = await self.jobs.tick()
            await self.jobs.nightly_backup(int(self.clock.now()))
        await self._flush(fx)

    async def _on_bridge_state(self, topic: str, payload: bytes) -> None:
        state = parse_state_value(payload)
        self.snapshots.extra_status["zigbee2mqtt"] = state
        self.jobs.bridge_state(state)
        self.sender.zigbee_up = state == "online"
        if state == "online":
            await self._flush(Effects(wake=await self._all_device_ids()))
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

    async def _all_device_ids(self) -> set[str]:
        from sqlalchemy import select
        from .db.models import Device
        async with self.sessions() as s:
            return {d for (d,) in (await s.execute(select(Device.id).where(Device.deleted_at.is_(None)))).all()}
