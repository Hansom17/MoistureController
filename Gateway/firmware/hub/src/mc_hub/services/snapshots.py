"""Builds the retained snapshots (Gateway/specs.md 3.4) from the database."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mc_hub import __version__
from mc_hub.bus.publisher import Publisher
from mc_hub.db.models import Alert, Device, Plant, Reading, Rule, Setting

from .views import alert_view, device_view, plant_view, rule_view

NAMES = ("installation", "devices", "plants", "rules", "alerts_open", "join", "status")


class Snapshots:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], pub: Publisher):
        self.sessions, self.pub = sessions, pub
        self.extra_status: dict = {"zigbee2mqtt": "unknown", "coordinator": "unknown", "clock_synced": True}
        self.join: dict = {"open": False, "ends_at": None, "devices": []}

    async def get_setting(self, s: AsyncSession, key: str, default=None):
        row = await s.get(Setting, key)
        return default if row is None else row.value

    async def build(self, s: AsyncSession, name: str) -> dict | list:
        if name == "installation":
            tg = await self.get_setting(s, "telegram") or {}
            return {"name": await self.get_setting(s, "name", ""),
                    "timezone": await self.get_setting(s, "timezone", "UTC"),
                    "battery_low_mv": await self.get_setting(s, "battery_low_mv", 3500),
                    "telegram_configured": bool(tg.get("token") and tg.get("chat_id"))}
        if name == "devices":
            rows = (await s.execute(select(Device).where(Device.deleted_at.is_(None)).order_by(Device.created_at))).scalars()
            return [device_view(d) for d in rows]
        if name == "plants":
            out = []
            for p in (await s.execute(select(Plant).where(Plant.archived_at.is_(None)).order_by(Plant.created_at))).scalars():
                latest = None
                if p.id:
                    r = (await s.execute(select(Reading).where(Reading.plant_id == p.id)
                                         .order_by(Reading.ts.desc(), Reading.id.desc()).limit(1))).scalar_one_or_none()
                    if r is not None:
                        latest = {"value": r.value, "ts": r.ts}
                out.append(plant_view(p, latest))
            return out
        if name == "rules":
            return [rule_view(r) for r in (await s.execute(select(Rule).where(Rule.deleted_at.is_(None)).order_by(Rule.plant_id, Rule.id))).scalars()]
        if name == "alerts_open":
            rows = (await s.execute(select(Alert).where(Alert.resolved_at.is_(None)).order_by(Alert.opened_at))).scalars()
            return [alert_view(a) for a in rows]
        if name == "join":
            return self.join
        if name == "status":
            return {**self.extra_status, "hub_version": __version__}
        raise KeyError(name)

    async def publish(self, names: set[str] | tuple[str, ...] = NAMES) -> None:
        async with self.sessions() as s:
            for n in names:
                await self.pub.snapshot(n, await self.build(s, n))
