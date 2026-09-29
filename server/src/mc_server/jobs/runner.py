"""Periodic jobs: expiry, late/offline, gateway offline, cleanup."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from ..context import AppContext, Uow
from ..db.models import Device, Downlink, GatewayEnrollment
from ..db.types import utcnow
from ..services import alerts, commands, gateways

log = logging.getLogger(__name__)


async def device_status(uow: Uow) -> None:
    """late after 1 missed interval, offline after 3; paused while the
    household's gateway is offline (Api_Specs §8.3)."""
    now = utcnow()
    offline = await gateways.offline_households(uow)
    devices = await uow.s.scalars(select(Device).where(
        Device.deleted_at.is_(None), Device.next_expected_at.is_not(None),
        Device.status.in_(("online", "sleeping", "service", "late"))))
    for d in devices:
        if d.household_id in offline:
            continue
        interval = timedelta(seconds=d.wake_interval_s)
        overdue = now - d.next_expected_at
        if overdue > 3 * interval:
            d.status = "offline"
            await alerts.open_alert(uow, d.household_id, "device_offline", "device", d.id, d.name)
        elif overdue > interval and d.status != "late":
            d.status = "late"
        else:
            continue
        uow.emit(d.household_id, "device", {"id": d.id, "status": d.status})
    await uow.commit()


async def cleanup(uow: Uow) -> None:
    now = utcnow()
    await uow.s.execute(delete(Downlink).where(
        Downlink.acked_at.is_not(None), Downlink.acked_at < now - timedelta(days=7)))
    await uow.s.execute(delete(GatewayEnrollment).where(
        GatewayEnrollment.created_at < now - timedelta(hours=24)))
    # Devices never paired within 24 h are removed with their keys (§8.1).
    stale = (await uow.s.scalars(select(Device).where(
        Device.status == "new", Device.deleted_at.is_(None),
        Device.created_at < now - timedelta(hours=24)))).all()
    for d in stale:
        d.deleted_at, d.psk_enc, d.gateway = now, None, "none"
        uow.emit(d.household_id, "device", {"id": d.id, "deleted": True})
    await uow.commit()


JOBS = (commands.expire_overdue, device_status, gateways.raise_offline_alerts, cleanup)


async def run_once(ctx: AppContext) -> None:
    for job in JOBS:
        try:
            async with ctx.uow() as uow:
                await job(uow)
        except Exception:
            log.exception("job %s failed", job.__name__)


async def run_forever(ctx: AppContext) -> None:
    while True:
        await run_once(ctx)
        await asyncio.sleep(ctx.settings.jobs_interval_s)
