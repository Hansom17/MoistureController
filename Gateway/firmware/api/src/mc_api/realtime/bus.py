"""In-process SSE bus: ring buffer for Last-Event-ID, subscribers, one-time tickets (Gateway/specs.md 6.1)."""
import asyncio
import itertools
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

RING_SIZE = 200
TICKET_TTL_S = 60


@dataclass
class LiveEvent:
    id: int
    kind: str
    data: dict


CLOSE = LiveEvent(-1, "close", {})


@dataclass(eq=False)
class Subscriber:
    user_id: str
    token_id: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=500))


class EventBus:
    def __init__(self, now=time.time) -> None:
        self._now = now
        # ids start at the process start time: ids of a previous process are lower, so those clients resync
        self._start = int(now() * 1000)
        self._ids = itertools.count(self._start)
        self._ring: deque[LiveEvent] = deque(maxlen=RING_SIZE)
        self._evicted = 0
        self._subs: set[Subscriber] = set()
        self._tickets: dict[str, tuple[str, str, float]] = {}

    def publish(self, kind: str, data: dict | None = None) -> None:
        ev = LiveEvent(next(self._ids), kind, data or {})
        if len(self._ring) == RING_SIZE:
            self._evicted = self._ring[0].id
        self._ring.append(ev)
        for sub in list(self._subs):
            try:
                sub.queue.put_nowait(ev)
            except asyncio.QueueFull:               # slow client: tell it to reload instead
                while not sub.queue.empty():
                    sub.queue.get_nowait()
                sub.queue.put_nowait(LiveEvent(ev.id, "resync", {}))

    def close_user(self, user_id: str) -> None:
        for sub in list(self._subs):
            if sub.user_id == user_id:
                sub.queue.put_nowait(CLOSE)

    def close_token(self, token_id: str) -> None:
        for sub in list(self._subs):
            if sub.token_id == token_id:
                sub.queue.put_nowait(CLOSE)

    def subscribe(self, user_id: str, token_id: str, last_event_id: int | None) -> Subscriber:
        sub = Subscriber(user_id, token_id)
        if last_event_id is not None:
            if last_event_id < max(self._start, self._evicted):
                sub.queue.put_nowait(LiveEvent(self._ring[-1].id if self._ring else 0, "resync", {}))
            else:
                for e in self._ring:
                    if e.id > last_event_id:
                        sub.queue.put_nowait(e)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    # tickets: the browser's EventSource cannot send an Authorization header
    def issue_ticket(self, user_id: str, token_id: str) -> str:
        now = self._now()
        self._tickets = {k: v for k, v in self._tickets.items() if v[2] > now}
        t = secrets.token_urlsafe(24)
        self._tickets[t] = (user_id, token_id, now + TICKET_TTL_S)
        return t

    def redeem_ticket(self, ticket: str) -> tuple[str, str] | None:
        entry = self._tickets.pop(ticket, None)
        if entry is None or entry[2] < self._now():
            return None
        return entry[0], entry[1]
