"""Device lifecycle helpers shared by removal, reconcile and the join flow."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mc_hub.db.models import Command, Device, Plant, Rule

from .commands import OPEN, command_view
from .effects import Effects
from .views import device_view, plant_view, rule_view


async def soft_delete(s: AsyncSession, fx: Effects, now: int, d: Device) -> None:
    """Remove a device from the working set; its history stays."""
    d.deleted_at = d.updated_at = now
    for c in (await s.execute(select(Command).where(Command.device_id == d.id, Command.status.in_(OPEN)))).scalars():
        c.status, c.reason, c.finished_at, c.updated_at = "cancelled", "device_removed", now, now
        fx.emit("command", command_view(c))
    plants = (await s.execute(select(Plant).where(
        (Plant.sensor_device_id == d.id) | (Plant.pump_device_id == d.id)))).scalars().all()
    for p in plants:
        pump_gone = p.pump_device_id == d.id
        if p.sensor_device_id == d.id:
            p.sensor_device_id = p.sensor_slot = None
        if pump_gone:
            p.pump_device_id = p.pump_slot = None
            for r in (await s.execute(select(Rule).where(Rule.plant_id == p.id, Rule.deleted_at.is_(None)))).scalars():
                r.enabled, r.updated_at = False, now
                fx.emit("rule", rule_view(r))
            fx.touch("rules")
        p.updated_at = now
        fx.emit("plant", plant_view(p))
        fx.touch("plants")
    fx.emit("device", device_view(d))
    fx.touch("devices")
