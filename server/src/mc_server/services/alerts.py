"""Alerts: one open alert per (kind, subject) (Api_Specs §11.2)."""

from sqlalchemy import select

from ..context import Uow
from ..db.models import Alert
from ..db.types import utcnow
from ..errors import Problem, not_found

TITLES = {
    "device_offline": "{name} is offline",
    "device_crashed": "{name} disconnected unexpectedly",
    "battery_low": "{name}: battery low",
    "sensor_error": "{name}: sensor error",
    "command_failed": "{name}: watering failed",
    "config_rejected": "{name}: configuration rejected",
    "safety_stop": "{name}: pump stopped by safety limit",
    "rule_limit_reached": "{name}: daily watering limit reached",
}

# Alerts that close only when a user acknowledges them.
ACK_ONLY = {"command_failed", "safety_stop", "rule_limit_reached"}


async def _open_alert(uow: Uow, household_id: str, kind: str, subject_id: str) -> Alert | None:
    return await uow.s.scalar(select(Alert).where(
        Alert.household_id == household_id, Alert.kind == kind,
        Alert.subject_id == subject_id, Alert.resolved_at.is_(None)))


async def open_alert(uow: Uow, household_id: str, kind: str, subject_type: str,
                     subject_id: str, subject_name: str | None, detail: dict | None = None,
                     severity: str = "warning") -> Alert:
    existing = await _open_alert(uow, household_id, kind, subject_id)
    if existing is not None:
        return existing
    alert = Alert(household_id=household_id, kind=kind, subject_type=subject_type,
                  subject_id=subject_id, subject_name=subject_name, detail=detail,
                  severity=severity)
    uow.s.add(alert)
    await uow.s.flush()
    uow.emit(household_id, "alert", {"id": alert.id, "kind": kind})
    uow.notify(household_id, TITLES.get(kind, kind).format(name=subject_name or ""),
               {"alert_id": alert.id, "kind": kind})
    return alert


async def resolve_alert(uow: Uow, household_id: str, kind: str, subject_id: str) -> None:
    alert = await _open_alert(uow, household_id, kind, subject_id)
    if alert is not None and kind not in ACK_ONLY:
        alert.resolved_at = utcnow()
        uow.emit(household_id, "alert", {"id": alert.id, "kind": kind})


async def acknowledge(uow: Uow, household_id: str, alert_id: str, uid: str) -> Alert:
    alert = await uow.s.scalar(select(Alert).where(
        Alert.id == alert_id, Alert.household_id == household_id))
    if alert is None:
        raise not_found("alert")
    if alert.acked_at is not None:
        raise Problem(409, "already_acknowledged")
    alert.acked_by, alert.acked_at = uid, utcnow()
    if alert.kind in ACK_ONLY and alert.resolved_at is None:
        alert.resolved_at = alert.acked_at
    uow.emit(household_id, "alert", {"id": alert.id})
    await uow.commit()
    return alert
