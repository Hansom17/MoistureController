"""In-process SSE bus: per-household ring buffers and subscribers (§6.2)."""

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


@dataclass(eq=False)  # hashed by identity
class _Subscriber:
    uid: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=500))


CLOSE = LiveEvent(-1, "close", {})


class EventBus:
    def __init__(self) -> None:
        # Ids start at the process start time, so ids from a previous process
        # are always lower and those clients get a resync.
        self._start_id = int(time.time() * 1000)
        self._ids = itertools.count(self._start_id)
        self._rings: dict[str, deque[LiveEvent]] = {}
        # Highest event id evicted from each ring; older clients must resync.
        self._evicted: dict[str, int] = {}
        self._subs: dict[str, set[_Subscriber]] = {}
        self._tickets: dict[str, tuple[str, float]] = {}

    # --- publishing -------------------------------------------------------------

    def publish(self, household_id: str, kind: str, data: dict | None = None) -> None:
        event = LiveEvent(next(self._ids), kind, data or {})
        ring = self._rings.setdefault(household_id, deque(maxlen=RING_SIZE))
        if len(ring) == RING_SIZE:
            self._evicted[household_id] = ring[0].id
        ring.append(event)
        for sub in list(self._subs.get(household_id, ())):
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow client: tell it to refetch everything instead.
                self._drain(sub.queue)
                sub.queue.put_nowait(LiveEvent(event.id, "resync", {}))

    def close_user(self, household_id: str, uid: str) -> None:
        """Ends the streams of a member who was removed."""
        for sub in list(self._subs.get(household_id, ())):
            if sub.uid == uid:
                sub.queue.put_nowait(CLOSE)

    # --- subscribing ------------------------------------------------------------

    def subscribe(self, household_id: str, uid: str, last_event_id: int | None) -> _Subscriber:
        sub = _Subscriber(uid)
        ring = self._rings.get(household_id, deque())
        if last_event_id is not None:
            if last_event_id < max(self._start_id, self._evicted.get(household_id, 0)):
                sub.queue.put_nowait(LiveEvent(ring[-1].id if ring else 0, "resync", {}))
            else:
                for e in ring:
                    if e.id > last_event_id:
                        sub.queue.put_nowait(e)
        self._subs.setdefault(household_id, set()).add(sub)
        return sub

    def unsubscribe(self, household_id: str, sub: _Subscriber) -> None:
        self._subs.get(household_id, set()).discard(sub)

    # --- tickets ----------------------------------------------------------------

    def issue_ticket(self, uid: str) -> str:
        now = time.monotonic()
        self._tickets = {t: v for t, v in self._tickets.items() if v[1] > now}
        ticket = secrets.token_urlsafe(24)
        self._tickets[ticket] = (uid, now + TICKET_TTL_S)
        return ticket

    def redeem_ticket(self, ticket: str) -> str | None:
        """Single use; returns the uid it was issued to."""
        entry = self._tickets.pop(ticket, None)
        if entry is None or entry[1] < time.monotonic():
            return None
        return entry[0]

    @staticmethod
    def _drain(q: asyncio.Queue) -> None:
        while not q.empty():
            q.get_nowait()
