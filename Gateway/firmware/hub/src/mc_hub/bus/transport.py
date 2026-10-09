"""MQTT transports behind one small interface.

`MemoryBroker` is an in-process broker for tests and the simulator (wildcards, retained
messages, last will, and fault injection: drop, duplicate, delay). `MqttTransport` talks to
a real broker with aiomqtt.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("mc_hub.bus")

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


class MemoryBroker:
    def __init__(self) -> None:
        self.retained: dict[str, bytes] = {}
        self.clients: list["MemoryTransport"] = []
        self.drop: Callable[[str, bytes], bool] | None = None
        self.duplicate: Callable[[str, bytes], bool] | None = None
        self.delay_s: float = 0.0
        self.log: list[tuple[str, bytes]] = []

    def client(self, will: Will | None = None) -> "MemoryTransport":
        return MemoryTransport(self, will)

    async def _route(self, topic: str, payload: bytes, retain: bool, sender: "MemoryTransport | None") -> None:
        self.log.append((topic, payload))
        if retain:
            if payload:
                self.retained[topic] = payload
            else:
                self.retained.pop(topic, None)
        if self.drop and self.drop(topic, payload):
            return
        copies = 2 if (self.duplicate and self.duplicate(topic, payload)) else 1
        for _ in range(copies):
            for c in list(self.clients):
                if c.connected:
                    await c._deliver(topic, payload, self.delay_s)


class MemoryTransport:
    def __init__(self, broker: MemoryBroker, will: Will | None = None) -> None:
        self.broker = broker
        self.will = will
        self.connected = False
        self.subs: list[tuple[str, Handler]] = []
        self._tasks: set[asyncio.Task] = set()

    async def connect(self) -> None:
        self.connected = True
        if self not in self.broker.clients:
            self.broker.clients.append(self)

    async def close(self, graceful: bool = True) -> None:
        self.connected = False
        if self in self.broker.clients:
            self.broker.clients.remove(self)
        if not graceful and self.will:
            await self.broker._route(self.will.topic, self.will.payload, self.will.retain, self)
        for t in list(self._tasks):
            t.cancel()

    async def kill(self) -> None:
        """Connection lost: the broker publishes the last will."""
        await self.close(graceful=False)

    async def publish(self, topic: str, payload: bytes, retain: bool = False) -> None:
        if not self.connected:
            raise ConnectionError("not connected")
        await self.broker._route(topic, payload, retain, self)

    async def subscribe(self, flt: str, handler: Handler) -> None:
        self.subs.append((flt, handler))
        for topic, payload in list(self.broker.retained.items()):
            if topic_matches(flt, topic):
                await self._dispatch(handler, topic, payload, 0)

    async def _deliver(self, topic: str, payload: bytes, delay: float) -> None:
        for flt, handler in list(self.subs):
            if topic_matches(flt, topic):
                await self._dispatch(handler, topic, payload, delay)

    async def _dispatch(self, handler: Handler, topic: str, payload: bytes, delay: float) -> None:
        async def run() -> None:
            if delay:
                await asyncio.sleep(delay)
            try:
                await handler(topic, payload)
            except Exception:  # a failing handler must not break the broker
                log.exception("handler failed for %s", topic)

        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def settle(self) -> None:
        """Wait until all in-flight deliveries are handled (tests)."""
        while True:
            pending = [t for t in self._tasks if not t.done()]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.sleep(0)


class MqttTransport:
    """Real broker via aiomqtt, with reconnect."""

    def __init__(self, host: str, port: int, user: str | None = None, password: str | None = None,
                 will: Will | None = None, client_id: str | None = None) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.will = will
        self.client_id = client_id
        self.subs: list[tuple[str, Handler]] = []
        self._client = None
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self.on_reconnect: list[Callable[[], Awaitable[None]]] = []   # run after every reconnect (not the first connect)
        self._connected_before = False

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
                async with aiomqtt.Client(self.host, self.port, username=self.user, password=self.password,
                                          will=will, identifier=self.client_id) as client:
                    self._client = client
                    for flt, _ in self.subs:
                        await client.subscribe(flt, qos=1)
                    reconnected, self._connected_before = self._connected_before, True
                    self._ready.set()
                    if reconnected:
                        for cb in self.on_reconnect:
                            asyncio.create_task(self._safe_cb(cb))
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
    async def _safe_cb(cb) -> None:
        try:
            await cb()
        except Exception:
            log.exception("reconnect callback failed")

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
