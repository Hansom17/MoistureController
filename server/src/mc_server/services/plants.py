"""Plants, readings, rules (Server_Specs §6.1)."""

from datetime import datetime, timedelta

from sqlalchemy import select

from ..context import Uow
from ..db.models import Device, Plant, ReadingRow, Rule, RuleExecution
from ..db.types import utcnow
from ..errors import Problem, not_found
from . import hubs
from .devices import actuator

TREND_WINDOW = timedelta(hours=3)
TREND_DELTA = 2.0  # percentage points


async def _check_slot(uow: Uow, household_id: str, device_id: str | None, slot: int | None,
                      what: str) -> None:
    if (device_id is None) != (slot is None):
        raise Problem(422, "out_of_range", f"{what}: device and slot go together")
    if device_id is None:
        return
    device = await uow.s.get(Device, device_id)
    if device is None or device.household_id != household_id or device.deleted_at:
        raise Problem(422, "unknown_device", what)


async def create(uow: Uow, household_id: str, data: dict, uid: str) -> Plant:
    await _check_slot(uow, household_id, data.get("sensor_device_id"), data.get("sensor_slot"),
                      "sensor")
    await _check_slot(uow, household_id, data.get("pump_device_id"), data.get("pump_slot"), "pump")
    plant = Plant(household_id=household_id, **data)
    uow.s.add(plant)
    await uow.s.flush()
    await hubs.republish_snapshot(uow, household_id)
    uow.emit(household_id, "plant", {"id": plant.id})
    await uow.commit()
    return plant


async def update(uow: Uow, plant: Plant, data: dict) -> Plant:
    merged = {k: data.get(k, getattr(plant, k)) for k in
              ("sensor_device_id", "sensor_slot", "pump_device_id", "pump_slot")}
    await _check_slot(uow, plant.household_id, merged["sensor_device_id"],
                      merged["sensor_slot"], "sensor")
    await _check_slot(uow, plant.household_id, merged["pump_device_id"],
                      merged["pump_slot"], "pump")
    for k, v in data.items():
        setattr(plant, k, v)
    await hubs.republish_snapshot(uow, plant.household_id)
    uow.emit(plant.household_id, "plant", {"id": plant.id})
    await uow.commit()
    return plant


async def archive(uow: Uow, plant: Plant) -> None:
    plant.archived_at = utcnow()
    for r in await uow.s.scalars(select(Rule).where(Rule.plant_id == plant.id)):
        r.enabled = False
    await hubs.republish_snapshot(uow, plant.household_id)
    uow.emit(plant.household_id, "plant", {"id": plant.id, "archived": True})
    await uow.commit()


async def view(uow: Uow, plant: Plant) -> dict:
    """Plant plus what the dashboard shows: latest value, trend, pump limit."""
    latest = await uow.s.scalar(select(ReadingRow).where(
        ReadingRow.plant_id == plant.id, ReadingRow.type == "soil_moisture")
        .order_by(ReadingRow.ts.desc()).limit(1))
    trend = "steady"
    if latest is not None and latest.value is not None:
        earlier = await uow.s.scalar(select(ReadingRow.value).where(
            ReadingRow.plant_id == plant.id, ReadingRow.type == "soil_moisture",
            ReadingRow.value.is_not(None), ReadingRow.ts <= latest.ts - TREND_WINDOW)
            .order_by(ReadingRow.ts.desc()).limit(1))
        if earlier is not None:
            delta = latest.value - earlier
            trend = "rising" if delta > TREND_DELTA else "falling" if delta < -TREND_DELTA \
                else "steady"
    max_run_s = None
    if plant.pump_device_id:
        device = await uow.s.get(Device, plant.pump_device_id)
        act = actuator(device, plant.pump_slot) if device else None
        if act is not None:
            max_run_s = min(act.max_run_s, act.hard_limit_s or act.max_run_s)
    return {
        "id": plant.id,
        "name": plant.name,
        "notes": plant.notes,
        "sensor_device_id": plant.sensor_device_id,
        "sensor_slot": plant.sensor_slot,
        "pump_device_id": plant.pump_device_id,
        "pump_slot": plant.pump_slot,
        "moisture": None if latest is None else latest.value,
        "moisture_error": None if latest is None else latest.error,
        "last_reading_at": None if latest is None else latest.ts,
        "trend": trend,
        "max_run_s": max_run_s,
    }


async def list_plants(uow: Uow, household_id: str) -> list[Plant]:
    return list(await uow.s.scalars(select(Plant).where(
        Plant.household_id == household_id, Plant.archived_at.is_(None))
        .order_by(Plant.created_at)))


# --- readings -----------------------------------------------------------------------

BUCKETS = {"raw": None, "1h": 3600, "1d": 86400}


async def readings(uow: Uow, plant: Plant, start: datetime, end: datetime, bucket: str,
                   type_: str = "soil_moisture") -> list[dict]:
    if bucket not in BUCKETS:
        raise Problem(422, "out_of_range", "bucket must be raw, 1h or 1d")
    if bucket == "raw" and end - start > timedelta(days=7):
        raise Problem(422, "out_of_range", "raw is limited to 7 days")
    rows = (await uow.s.execute(select(ReadingRow.ts, ReadingRow.value, ReadingRow.error).where(
        ReadingRow.plant_id == plant.id, ReadingRow.type == type_,
        ReadingRow.ts >= start, ReadingRow.ts <= end).order_by(ReadingRow.ts))).all()
    size = BUCKETS[bucket]
    if size is None:
        return [{"ts": ts, "value": v, "error": e} for ts, v, e in rows]
    # Aggregated in Python so the query stays portable (SQLite/Postgres).
    out: dict[int, list[float]] = {}
    for ts, v, _ in rows:
        if v is not None:
            out.setdefault(int(ts.timestamp()) // size * size, []).append(v)
    from .common import to_dt

    return [{"ts": to_dt(k), "value": sum(vs) / len(vs), "min": min(vs), "max": max(vs)}
            for k, vs in sorted(out.items())]


# --- rules -----------------------------------------------------------------------------


def _validate_rule(data: dict) -> None:
    for key in ("quiet_from", "quiet_to"):
        v = data.get(key)
        if v is not None:
            try:
                h, m = v.split(":")
                assert 0 <= int(h) < 24 and 0 <= int(m) < 60 and len(v) == 5
            except (ValueError, AssertionError) as e:
                raise Problem(422, "out_of_range", f"{key} must be HH:MM") from e


async def get_rule(uow: Uow, plant: Plant, rule_id: str) -> Rule:
    rule = await uow.s.scalar(select(Rule).where(Rule.id == rule_id, Rule.plant_id == plant.id))
    if rule is None:
        raise not_found("rule")
    return rule


async def create_rule(uow: Uow, plant: Plant, data: dict, uid: str) -> Rule:
    _validate_rule(data)
    rule = Rule(household_id=plant.household_id, plant_id=plant.id, created_by=uid, **data)
    uow.s.add(rule)
    await uow.s.flush()
    await hubs.republish_snapshot(uow, plant.household_id)
    uow.emit(plant.household_id, "rule", {"plant_id": plant.id})
    await uow.commit()
    return rule


async def update_rule(uow: Uow, rule: Rule, data: dict) -> Rule:
    _validate_rule(data)
    for k, v in data.items():
        setattr(rule, k, v)
    await hubs.republish_snapshot(uow, rule.household_id)
    uow.emit(rule.household_id, "rule", {"plant_id": rule.plant_id})
    await uow.commit()
    return rule


async def delete_rule(uow: Uow, rule: Rule) -> None:
    hid, pid = rule.household_id, rule.plant_id
    await uow.s.delete(rule)
    await hubs.republish_snapshot(uow, hid)
    uow.emit(hid, "rule", {"plant_id": pid})
    await uow.commit()


async def executions(uow: Uow, rule: Rule, limit: int = 50) -> list[RuleExecution]:
    return list(await uow.s.scalars(select(RuleExecution).where(
        RuleExecution.rule_id == rule.id).order_by(RuleExecution.ts.desc()).limit(limit)))

