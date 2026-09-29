"""The WebSocket to the API server (gateway_api.md §4).

One outbound connection: `hello` → `welcome{ack_seq}`, then the outbox is
replayed from `ack_seq` and new entries follow as they are written. Down
messages are applied through the agent and confirmed with `down_ack`.
`Uplink.run()` returns only when the gateway was removed in the app.
"""

import asyncio
import json
import logging
import random

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .agent import Agent
from .config import VERSION, HubConfig

log = logging.getLogger(__name__)

WELCOME_TIMEOUT_S = 30
IDLE_POLL_S = 5  # also picks up entries written by `mc-hub` CLI processes
BATCH = 100
MAX_BACKOFF_S = 60
REJECTIONS_UNTIL_REMOVED = 3  # gateway_api.md §4


def ws_url(api_url: str) -> str:
    base = api_url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return f"{base}/gateway/v1/connect"


class Removed(Exception):
    """The API removed this gateway: forget the enrollment."""


class Uplink:
    def __init__(self, cfg: HubConfig, agent: Agent, connector=connect):
        self.cfg = cfg
        self.agent = agent
        self.url = ws_url(cfg.api_url)
        self._connect = connector
        self._new = asyncio.Event()
        self.connected = False

    async def run(self) -> None:
        self.agent.on_report = self._new.set
        backoff, rejections = 1.0, 0
        try:
            while True:
                try:
                    headers = {"Authorization":
                               f"Gateway {self.agent.gateway_id}:{self.agent.credential}"}
                    async with self._connect(self.url, additional_headers=headers,
                                             ping_interval=30, ping_timeout=30,
                                             max_size=2**20) as ws:
                        backoff, rejections = 1.0, 0
                        await self._session(ws)
                except Removed:
                    log.warning("gateway removed by the API server")
                    return
                except InvalidStatus as e:
                    status = e.response.status_code
                    if status in (401, 403):
                        rejections += 1
                        log.warning("API rejected the credential (%s, %d×)", status, rejections)
                        if rejections >= REJECTIONS_UNTIL_REMOVED:
                            return
                    else:
                        log.warning("API connection refused: HTTP %s", status)
                except ConnectionClosed as e:
                    code = e.rcvd.code if e.rcvd else None
                    if code == 4001:
                        return
                    log.warning("API connection closed (%s)", code)
                except (OSError, TimeoutError) as e:
                    log.warning("API unreachable: %s", e)
                finally:
                    self.connected = False
                delay = backoff * random.uniform(0.8, 1.2)
                log.info("reconnecting to the API in %.0fs", delay)
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
        finally:
            self.agent.on_report = None

    async def _session(self, ws: ClientConnection) -> None:
        store = self.agent.store
        depth, _ = store.outbox_depth()
        await ws.send(json.dumps({
            "t": "hello", "version": VERSION, "adapters": list(self.cfg.adapters),
            "snapshot_rev": store.get_int("snapshot_rev"), "keys_rev": store.get_int("keys_rev"),
            "last_down_id": store.get("last_down_id"), "outbox_depth": depth,
            "lan_host": self.cfg.lan_host, "time_synced": self.agent.time_synced()}))
        welcome = json.loads(await asyncio.wait_for(ws.recv(), WELCOME_TIMEOUT_S))
        if welcome.get("t") != "welcome":
            raise ConnectionError(f"expected welcome, got {welcome.get('t')!r}")
        store.outbox_ack(int(welcome["ack_seq"]))
        self.connected = True
        log.info("connected to the API (acked up to seq %s, %d to replay)", welcome["ack_seq"],
                 store.outbox_depth()[0])
        self.agent.publish_state()  # current LAN address and revisions right away
        sender = asyncio.create_task(self._sender(ws, int(welcome["ack_seq"])))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                t = msg.get("t")
                if t == "ack":
                    store.outbox_ack(int(msg["seq"]))
                elif t in ("welcome", "ping"):
                    pass
                elif t == "removed":
                    raise Removed
                else:
                    ack = await self._apply(msg)
                    if ack is not None:
                        await ws.send(json.dumps(ack))
                        store.set("last_down_id", msg.get("id"))
                    if t == "rotate_credential":
                        await ws.close()  # reconnect with the new credential
                if sender.done():
                    sender.result()  # re-raise its error
        finally:
            sender.cancel()

    async def _sender(self, ws: ClientConnection, sent: int) -> None:
        """Outbox entries after `sent`, in order; waits for new ones when caught up."""
        while True:
            self._new.clear()
            batch = self.agent.store.outbox_peek(BATCH, after=sent)
            for msg in batch:
                await ws.send(json.dumps(msg, separators=(",", ":")))
                sent = msg["seq"]
            if len(batch) < BATCH:
                try:
                    await asyncio.wait_for(self._new.wait(), IDLE_POLL_S)
                except TimeoutError:
                    pass

    async def _apply(self, msg: dict) -> dict | None:
        """The `down_ack`, or None to leave it unconfirmed (re-sent after a reconnect)."""
        t, agent = msg.get("t"), self.agent
        try:
            match t:
                case "keys":
                    return agent.apply_keys(msg)
                case "snapshot":
                    return agent.apply_snapshot(msg)
                case "command":
                    return await agent.apply_command(msg)
                case "config_desired":
                    return await agent.apply_config(msg)
                case "device_removed":
                    return await agent.apply_device_removed(msg)
                case "rotate_credential":
                    agent.store_credential(msg["credential"])
                    return agent._down_ack(msg.get("id"))
                case _:
                    log.info("unknown down message %r", t)
                    return agent._down_ack(msg.get("id"), "rejected", "unknown_type")
        except (ValidationError, KeyError) as e:
            return agent._down_ack(msg.get("id"), "rejected", str(e)[:200])
        except RuntimeError as e:  # local broker not connected
            log.warning("can't apply %s now: %s", t, e)
            if t == "command":  # a late command is worse than a failed one
                return agent._down_ack(msg.get("id"), "rejected", "broker_unavailable")
            return None
