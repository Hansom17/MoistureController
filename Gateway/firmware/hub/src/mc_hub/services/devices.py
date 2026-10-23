"""Device lifecycle helpers shared by removal, reconcile and the join flow."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mc_hub.db.models import Alert, Command, ConfigRevision, Device, Plant, Rule

from .commands import OPEN, command_view
from .effects import Effects
from .views import device_view, plant_view, rule_view


async def bury(s: AsyncSession, now: int, d: Device) -> None:
    """Wipe what a removed device had configured and free its Zigbee address.

    The row stays as a tombstone for the history that points at it (readings, commands, events), but nothing of its
    configuration survives, and a device that joins later with the same address is a new device with a new id."""
    await s.execute(delete(ConfigRevision).where(ConfigRevision.device_id == d.id))
    for a in (await s.execute(select(Alert).where(Alert.subject_type == "device", Alert.subject_id == d.id,
                                                 Alert.resolved_at.is_(None)))).scalars():
        a.resolved_at = a.updated_at = now
    if "~" not in d.ieee:
        d.ieee = f"{d.ieee}~{d.id}"
    d.desired_config = d.reported_config = d.config_error = d.slots = d.diagnostics = d.sensor_error_streak = None
    d.desired_rev, d.reported_rev, d.rejected_rev = 0, None, None
    d.batt_state = d.batt_hist = d.voltage_mv = None
    if d.deleted_at is None:
        d.deleted_at = now
    d.updated_at = now


async def soft_delete(s: AsyncSession, fx: Effects, now: int, d: Device) -> None:
    """Remove a device from the working set; only its history stays (see `bury`)."""
    await bury(s, now, d)
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
