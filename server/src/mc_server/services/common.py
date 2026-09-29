import time
from datetime import UTC, datetime

from sqlalchemy import select

from ..context import Uow
from ..db.models import AuditLog, Device, Hub, Plant
from ..errors import not_found


def now_ts() -> int:
    return int(time.time())


def to_dt(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def to_ts(dt: datetime | None) -> int | None:
    return None if dt is None else int(dt.timestamp())


async def get_device(uow: Uow, household_id: str, device_id: str) -> Device:
    device = await uow.s.scalar(select(Device).where(
        Device.id == device_id, Device.household_id == household_id, Device.deleted_at.is_(None)))
    if device is None:
        raise not_found("device")
    return device


async def get_plant(uow: Uow, household_id: str, plant_id: str) -> Plant:
    plant = await uow.s.scalar(select(Plant).where(
        Plant.id == plant_id, Plant.household_id == household_id, Plant.archived_at.is_(None)))
    if plant is None:
        raise not_found("plant")
    return plant


async def get_hub(uow: Uow, household_id: str) -> Hub | None:
    return await uow.s.scalar(select(Hub).where(Hub.household_id == household_id))


def audit(uow: Uow, household_id: str | None, actor: str | None, action: str,
          detail: dict | None = None, ip: str | None = None) -> None:
    uow.s.add(AuditLog(household_id=household_id, actor=actor, action=action,
                       detail=detail, ip=ip))
