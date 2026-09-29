"""MQTT connection: ingest subscriber + outbox sender (Server_Specs §10.1)."""

import asyncio
import logging

import aiomqtt
from sqlalchemy import select

from ..context import AppContext
from ..db.models import Outbox
from ..db.types import utcnow
from ..services import ingest

log = logging.getLogger(__name__)

SUBSCRIPTIONS = [
    "mc/v1/+/status",
    "mc/v1/+/telemetry",
    "mc/v1/+/event",
    "mc/v1/+/cmd/ack",
    "mc/v1/+/config/state",
    "mc/hub/v1/+/up/#",
]
OUTBOX_BATCH = 100
OUTBOX_POLL_S = 5


class MqttService:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.connected = asyncio.Event()

    async def run_forever(self) -> None:
        s = self.ctx.settings
        backoff = 1
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=s.mqtt_host, port=s.mqtt_port, identifier="mc-backend",
                    username=s.mqtt_username, password=s.mqtt_password,
                    clean_session=False, keepalive=60,
                ) as client:
                    backoff = 1
                    for topic in SUBSCRIPTIONS:
                        await client.subscribe(topic, qos=1)
                    self.connected.set()
                    log.info("MQTT connected to %s:%s", s.mqtt_host, s.mqtt_port)
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._receive(client))
                        tg.create_task(self._send_outbox(client))
            except* aiomqtt.MqttError as eg:
                log.warning("MQTT connection lost: %s; retrying in %ss", eg.exceptions[0], backoff)
            self.connected.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _receive(self, client: aiomqtt.Client) -> None:
        # Sequential on purpose: per-device order matters (acks after cmds, …).
        async for message in client.messages:
            payload = message.payload if isinstance(message.payload, bytes) else (
                str(message.payload).encode() if message.payload is not None else b"")
            try:
                async with self.ctx.uow() as uow:
                    await ingest.handle(uow, str(message.topic), payload, message.retain)
            except Exception:
                log.exception("ingest failed for %s", message.topic)

    async def _send_outbox(self, client: aiomqtt.Client) -> None:
        while True:
            await send_pending(self.ctx, client.publish)
            try:
                await asyncio.wait_for(self.ctx.outbox_wakeup.wait(), OUTBOX_POLL_S)
            except TimeoutError:
                pass
            self.ctx.outbox_wakeup.clear()


async def send_pending(ctx: AppContext, publish) -> int:
    """Publishes unsent outbox rows in order; marks each sent after PUBACK."""
    sent = 0
    while True:
        async with ctx.sessionmaker() as s:
            rows = list(await s.scalars(select(Outbox).where(Outbox.sent_at.is_(None))
                                        .order_by(Outbox.id).limit(OUTBOX_BATCH)))
            if not rows:
                return sent
            for row in rows:
                payload = b"" if row.payload is None else row.payload.encode()
                await publish(row.topic, payload, qos=row.qos, retain=row.retain)
                row.sent_at = utcnow()
                await s.commit()
                sent += 1
