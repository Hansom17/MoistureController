"""Periodic jobs: expiry, late/offline, hub alerts, cleanup (Server_Specs §3)."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from ..context import AppContext, Uow
from ..db.models import Device, Hub, HubEnrollment, Outbox
from ..db.types import utcnow
from ..services import alerts, commands, hubs

log = logging.getLogger(__name__)


async def device_status(uow: Uow) -> None:
    """late after 1 missed interval, offline after 3 (§8.3); paused while hub offline."""
    now = utcnow()
    offline_hubs = set((await uow.s.scalars(select(Hub.household_id).where(
        Hub.bridge_connected.is_(False)))).all())
    devices = await uow.s.scalars(select(Device).where(
        Device.deleted_at.is_(None), Device.next_expected_at.is_not(None),
        Device.status.in_(("online", "sleeping", "service", "late"))))
    for d in devices:
        if d.gateway == "hub" and d.household_id in offline_hubs:
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
    await uow.s.execute(delete(HubEnrollment).where(
        HubEnrollment.created_at < now - timedelta(hours=24)))
    await uow.s.execute(delete(Outbox).where(
        Outbox.sent_at.is_not(None), Outbox.sent_at < now - timedelta(days=7)))
    # Devices never paired within 24 h are removed with their keys (§8.1).
    stale = (await uow.s.scalars(select(Device).where(
        Device.status == "new", Device.deleted_at.is_(None),
        Device.created_at < now - timedelta(hours=24)))).all()
    for d in stale:
        d.deleted_at, d.psk_enc, d.gateway = now, None, "none"
        uow.emit(d.household_id, "device", {"id": d.id, "deleted": True})
    if stale:
        uow.broker_files_changed()
    await uow.commit()


JOBS = (commands.expire_overdue, device_status, hubs.raise_offline_alerts, cleanup)


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
