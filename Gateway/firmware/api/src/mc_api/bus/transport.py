"""MQTT transport (aiomqtt) behind a small interface: connect / close / publish / subscribe.

Tests plug in any object with the same four methods (they use the hub package's in-memory broker).
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("mc_api.bus")

Handler = Callable[[str, bytes], Awaitable[None]]


def topic_matches(flt: str, topic: str) -> bool:
    f, t = flt.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(f) == len(t)


class Transport(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def publish(self, topic: str, payload: bytes, retain: bool = False) -> None: ...
    async def subscribe(self, flt: str, handler: Handler) -> None: ...


@dataclass
class Will:
    topic: str
    payload: bytes
    retain: bool = True


class MqttTransport:
    """Real broker via aiomqtt, with reconnect."""

    def __init__(self, host: str, port: int, user: str | None = None, password: str | None = None,
                 will: Will | None = None, client_id: str | None = None, ca: str | None = None) -> None:
        self.ca = ca
        self.host, self.port, self.user, self.password = host, port, user, password
        self.will = will
        self.client_id = client_id
        self.subs: list[tuple[str, Handler]] = []
        self._client = None
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()

    async def connect(self) -> None:
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._ready.wait(), timeout=30)

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        import aiomqtt

        while True:
            try:
                will = aiomqtt.Will(self.will.topic, self.will.payload, qos=1, retain=self.will.retain) if self.will else None
                tls = aiomqtt.TLSParameters(ca_certs=self.ca) if self.ca else None
                async with aiomqtt.Client(self.host, self.port, username=self.user, password=self.password,
                                          will=will, identifier=self.client_id, tls_params=tls) as client:
                    self._client = client
                    for flt, _ in self.subs:
                        await client.subscribe(flt, qos=1)
                    self._ready.set()
                    async for msg in client.messages:
                        for flt, handler in list(self.subs):
                            if topic_matches(flt, str(msg.topic)):
                                asyncio.create_task(self._safe(handler, str(msg.topic), bytes(msg.payload)))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("mqtt connection lost (%s), retrying in 3 s", e)
                self._client = None
                self._ready.clear()
                await asyncio.sleep(3)

    @staticmethod
    async def _safe(handler: Handler, topic: str, payload: bytes) -> None:
        try:
            await handler(topic, payload)
        except Exception:
            log.exception("handler failed for %s", topic)

    async def publish(self, topic: str, payload: bytes, retain: bool = False) -> None:
        if self._client is None:
            raise ConnectionError("mqtt not connected")
        await self._client.publish(topic, payload, qos=1, retain=retain)

    async def subscribe(self, flt: str, handler: Handler) -> None:
        self.subs.append((flt, handler))
        if self._client is not None:
            await self._client.subscribe(flt, qos=1)
