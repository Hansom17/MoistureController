"""Periodic work (Gateway/specs.md 9.2, 11): command expiry, late devices, sender retries."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mc_hub.clock import Clock
from mc_hub.db.models import Command, Device

from . import alerts
from .commands import command_view
from .effects import Effects
from .views import alert_view, device_view

LATE_AFTER_REPORTS = 3
DEFAULT_REPORT_INTERVAL_S = 300
ZIGBEE_DOWN_ALERT_S = 300
EXPIRY_GRACE_S = 30
NO_FINAL_ACK_S = 60


class Jobs:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self.sessions, self.clock = sessions, clock
        self.zigbee_down_since: float | None = None

    @property
    def zigbee_up(self) -> bool:
        return self.zigbee_down_since is None

    def bridge_state(self, state: str) -> None:
        if state == "online":
            self.zigbee_down_since = None
        elif self.zigbee_down_since is None:
            self.zigbee_down_since = self.clock.now()

    async def tick(self) -> Effects:
        fx = Effects()
        now = int(self.clock.now())
        async with self.sessions() as s:
            await self._zigbee_alert(s, fx, now)
            await self._expire(s, fx, now)
            if self.zigbee_up:        # a silent device proves nothing while Zigbee2MQTT is down
                await self._late(s, fx, now)
            for did in await self._devices_with_work(s):
                fx.kick(did)
            await s.commit()
        return fx

    async def _zigbee_alert(self, s: AsyncSession, fx: Effects, now: int) -> None:
        if self.zigbee_down_since is not None and now - self.zigbee_down_since > ZIGBEE_DOWN_ALERT_S:
            a, new = await alerts.open_alert(s, now, "zigbee_offline", "installation", "zigbee2mqtt", "Zigbee",
                                             severity="critical")
            if new:
                fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
                fx.notify("Zigbee2MQTT or the coordinator is not reachable", [], "alert", alert_kind="zigbee_offline")
        elif self.zigbee_down_since is None:
            for a in await alerts.resolve_alerts(s, now, "zigbee_offline", "installation", "zigbee2mqtt"):
                fx.emit("alert", alert_view(a)); fx.touch("alerts_open")

    async def _expire(self, s: AsyncSession, fx: Effects, now: int) -> None:
        rows = (await s.execute(select(Command).where(
            Command.status.in_(("queued", "cancelling", "delivered"))))).scalars().all()
        for c in rows:
            new = reason = None
            if c.status in ("queued", "cancelling"):
                if (c.sent_at is None and now >= c.exp) or (c.sent_at is not None and now > c.exp + EXPIRY_GRACE_S):
                    new, reason = "expired", "expired"
            elif c.ends_at is not None and now > c.ends_at + NO_FINAL_ACK_S:
                new, reason = "failed", "no_final_ack"
            if new is None:
                continue
            c.status, c.reason, c.finished_at, c.updated_at = new, reason, now, now
            fx.emit("command", command_view(c))
            if new == "failed" and c.action == "pump.run":
                d = await s.get(Device, c.device_id)
                a, opened = await alerts.open_alert(s, now, "command_failed", "command", c.id,
                                                    (d.name or d.id) if d else c.device_id, detail={"reason": reason})
                if opened:
                    fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
                    fx.notify(f"Watering failed: {reason}", [], "alert", alert_kind="command_failed")

    async def _late(self, s: AsyncSession, fx: Effects, now: int) -> None:
        rows = (await s.execute(select(Device).where(Device.status == "online", Device.deleted_at.is_(None)))).scalars()
        for d in rows:
            limit = LATE_AFTER_REPORTS * (d.report_interval_s or DEFAULT_REPORT_INTERVAL_S)
            if d.last_seen_at is not None and now - d.last_seen_at > limit:
                d.status, d.updated_at = "late", now
                fx.emit("device", device_view(d)); fx.touch("devices")

    async def _devices_with_work(self, s: AsyncSession) -> set[str]:
        ids = {c.device_id for c in (await s.execute(select(Command).where(Command.status == "queued"))).scalars()}
        for d in (await s.execute(select(Device).where(Device.deleted_at.is_(None), Device.desired_rev > 0))).scalars():
            if d.reported_rev != d.desired_rev and d.rejected_rev != d.desired_rev:
                ids.add(d.id)
        return ids
