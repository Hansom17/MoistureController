"""Sender (Gateway/specs.md 9.4): hands commands and configurations to Zigbee2MQTT.

Per device one item at a time: commands oldest first, then the newest unconfirmed configuration.
An item is in flight from sending until it is confirmed (ack / matching cfg_rev) or its attempt
timed out (10 s); after 3 attempts the device is given a rest until it reports again.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mc_hub.bus.transport import Transport
from mc_hub.clock import Clock
from mc_hub.db.models import Command, ConfigRevision, Device
from mc_hub.zigbee.topics import Z2MTopics

from .commands import command_view
from .effects import Effects

log = logging.getLogger("mc_hub.sender")

ATTEMPT_TIMEOUT_S = 10
RETRY_PAUSE_S = 2
MAX_ATTEMPTS = 3
COMMAND_STATUS_OK = ("ready", "online", "late")       # a device we can talk to
DEVICE_STATUS_OK = COMMAND_STATUS_OK + ("safe_mode",)  # safe mode: only device actions go out


def payload_for(c: Command, now: int, target_zb: int | None) -> dict:
    a = c.args or {}
    if c.action == "pump.run":
        return {"pump_run": {"cmd_id": c.zb_id, "slot": a["slot"], "seconds": a["seconds"],
                             "ttl_s": max(1, c.exp - now)}}
    if c.action == "pump.stop":
        return {"pump_stop": {"cmd_id": c.zb_id, "slot": a["slot"]}}
    if c.action == "cmd.cancel":
        return {"cancel": {"cmd_id": c.zb_id, "target": a["target"]}}
    action = c.action.split(".", 1)[1]
    return {"device_action": {"cmd_id": c.zb_id, "action": action, "arg": a.get("arg", 0)}}


class Sender:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], transport: Transport, topics: Z2MTopics,
                 clock: Clock) -> None:
        self.sessions, self.t, self.topics, self.clock = sessions, transport, topics, clock
        self.zigbee_up = True

    async def flush(self, device_id: str) -> Effects:
        """Look at one device and send the next item if there is one and nothing is in flight."""
        fx = Effects()
        now = int(self.clock.now())
        async with self.sessions() as s:
            d = await s.get(Device, device_id)
            if d is None or d.deleted_at is not None or d.status not in DEVICE_STATUS_OK:
                return fx
            if not self.zigbee_up:
                return fx
            cmds = (await s.execute(select(Command).where(
                Command.device_id == d.id, Command.status.in_(("queued", "cancelling", "delivered")))
                .order_by(Command.created_at, Command.id))).scalars().all()
            queued = [c for c in cmds if c.status == "queued"]
            # in flight: sent, no ack yet
            for c in queued:
                if c.sent_at is not None and (c.attempts >= MAX_ATTEMPTS or now < self._next_try(c)):
                    return fx            # waiting for the ack, the next attempt or a new report
                if c.sent_at is not None and c.attempts < MAX_ATTEMPTS:
                    await self._send_command(s, fx, d, c, now)
                    await s.commit()
                    return fx
            for c in queued:
                if c.sent_at is None and c.exp > now:
                    if d.status == "safe_mode" and not c.action.startswith("device."):
                        continue
                    await self._send_command(s, fx, d, c, now)
                    await s.commit()
                    return fx
            if d.status != "safe_mode":
                await self._send_config(s, d, now)
                await s.commit()
        return fx

    @staticmethod
    def _next_try(c) -> int:
        return (c.last_attempt_at or 0) + ATTEMPT_TIMEOUT_S + RETRY_PAUSE_S

    async def _send_command(self, s: AsyncSession, fx: Effects, d: Device, c: Command, now: int) -> None:
        await self.t.publish(self.topics.set(d.id), json.dumps(payload_for(c, now, None)).encode())
        c.attempts += 1
        c.last_attempt_at = now
        if c.sent_at is None:
            c.sent_at = now
        c.updated_at = now
        fx.emit("command", command_view(c))

    async def _send_config(self, s: AsyncSession, d: Device, now: int) -> None:
        if d.desired_rev == 0 or d.reported_rev == d.desired_rev or d.rejected_rev == d.desired_rev:
            return
        rev = await s.get(ConfigRevision, (d.id, d.desired_rev))
        if rev is None:
            return
        if rev.sent_at is not None:
            if rev.attempts >= MAX_ATTEMPTS or now < (rev.last_attempt_at or 0) + ATTEMPT_TIMEOUT_S + RETRY_PAUSE_S:
                return
        await self.t.publish(self.topics.set(d.id), json.dumps({"config": rev.body}).encode())
        rev.attempts += 1
        rev.last_attempt_at = now
        rev.sent_at = rev.sent_at or now

    async def device_returned(self, device_id: str) -> None:
        """A report arrived: give an item that used up its attempts a fresh start."""
        async with self.sessions() as s:
            for c in (await s.execute(select(Command).where(
                    Command.device_id == device_id, Command.status == "queued",
                    Command.attempts >= MAX_ATTEMPTS))).scalars():
                c.attempts = 0
            d = await s.get(Device, device_id)
            if d is not None and d.desired_rev:
                rev = await s.get(ConfigRevision, (d.id, d.desired_rev))
                if rev is not None and rev.attempts >= MAX_ATTEMPTS:
                    rev.attempts = 0
            await s.commit()
