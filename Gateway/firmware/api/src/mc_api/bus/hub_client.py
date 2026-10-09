"""Talking to `hub` over MQTT (Gateway/specs.md section 3): requests, events, snapshots, status."""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from ulid import ULID

from mc_api import CONTRACT
from mc_api.clock import Clock
from mc_api.errors import ApiError

log = logging.getLogger("mc_api.hub")
V = 1
P = "mc/v1"


class HubClient:
    def __init__(self, transport, instance: str, clock: Clock, timeout_s: float = 10.0) -> None:
        self.t, self.instance, self.clock, self.timeout_s = transport, instance, clock, timeout_s
        self.state: dict[str, Any] = {}            # retained snapshots, by name
        self.hub_status: dict | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self._last: tuple[int, int] | None = None   # (boot_id, seq) of the last hub event
        self.on_event: Callable[[str, dict], Awaitable[None]] | None = None
        self.on_resync: Callable[[], Awaitable[None]] | None = None
        self.on_status: Callable[[], Awaitable[None]] | None = None

    async def start(self) -> None:
        await self.t.subscribe(f"{P}/res/{self.instance}/#", self._on_response)
        await self.t.subscribe(f"{P}/event/#", self._on_event)
        await self.t.subscribe(f"{P}/state/#", self._on_state)
        await self.t.subscribe(f"{P}/status/hub", self._on_status)

    # ---- state of the hub ---------------------------------------------------------------------

    @property
    def online(self) -> bool:
        return bool(self.hub_status and self.hub_status.get("state") == "online")

    @property
    def compatible(self) -> bool:
        return bool(self.hub_status) and str(self.hub_status.get("contract", "")).split(".")[0] == CONTRACT.split(".")[0]

    # ---- requests ------------------------------------------------------------------------------

    async def request(self, kind: str, body: dict, actor: dict, timeout: float | None = None) -> dict:
        if not self.online:
            raise ApiError("hub_unavailable", "The watering service is not reachable")
        if not self.compatible:
            raise ApiError("incompatible_hub", "The hub speaks a different contract version")
        timeout = timeout or self.timeout_s
        id = str(ULID())
        now = datetime.fromtimestamp(self.clock.now(), timezone.utc)
        env = {"v": V, "id": id, "ts": now.isoformat(), "deadline": (now + timedelta(seconds=timeout)).isoformat(),
               "reply_to": f"{P}/res/{self.instance}/{id}", "actor": actor, "body": body}
        fut = asyncio.get_running_loop().create_future()
        self.pending[id] = fut
        try:
            await self.t.publish(f"{P}/req/hub/{kind}", json.dumps(env).encode())
            res = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            raise ApiError("hub_timeout", "The hub did not answer in time",
                           "The action may still have happened; reload to see the current state.")
        except ConnectionError:
            raise ApiError("hub_unavailable", "The message bus is not reachable")
        finally:
            self.pending.pop(id, None)
        if res.get("ok"):
            return res.get("body", {})
        e = res.get("error", {})
        raise ApiError(e.get("type", "internal"), e.get("title", ""), e.get("detail", ""), status=e.get("status"))

    async def publish_event(self, kind: str, body: dict) -> None:
        env = {"v": V, "ts": datetime.fromtimestamp(self.clock.now(), timezone.utc).isoformat(), "kind": kind,
               "body": body}
        try:
            await self.t.publish(f"{P}/event/api/{kind}", json.dumps(env).encode())
        except ConnectionError:
            log.warning("could not publish api event %s", kind)

    # ---- incoming -----------------------------------------------------------------------------

    async def _on_response(self, topic: str, payload: bytes) -> None:
        try:
            res = json.loads(payload)
        except ValueError:
            return
        fut = self.pending.get(res.get("id"))
        if fut is not None and not fut.done():
            fut.set_result(res)

    async def _on_state(self, topic: str, payload: bytes) -> None:
        name = topic[len(f"{P}/state/"):]
        if not payload:
            self.state.pop(name, None)
            return
        try:
            self.state[name] = json.loads(payload)
        except ValueError:
            log.warning("bad snapshot %s", name)

    async def _on_status(self, topic: str, payload: bytes) -> None:
        try:
            self.hub_status = json.loads(payload) if payload else None
        except ValueError:
            return
        if not self.online:
            for fut in list(self.pending.values()):      # a request cannot be answered by a hub that is gone
                if not fut.done():
                    fut.set_exception(ApiError("hub_unavailable", "The watering service went away"))
        if self.on_status:
            await self.on_status()

    async def _on_event(self, topic: str, payload: bytes) -> None:
        if topic.startswith(f"{P}/event/api/"):
            return
        try:
            ev = json.loads(payload)
        except ValueError:
            return
        key = (ev.get("boot_id"), ev.get("seq"))
        gap = self._last is None or key[0] != self._last[0] or key[1] != self._last[1] + 1
        first = self._last is None
        self._last = key
        if gap and not first and self.on_resync:
            await self.on_resync()          # the snapshots are current; browsers just have to reload
        if self.on_event:
            await self.on_event(ev.get("kind", ""), ev.get("body", {}))
