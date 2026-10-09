from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from mc_hub.db.models import Alert
from mc_hub.errors import HubError

from .views import alert_view


async def open_alert(s: AsyncSession, now: int, kind: str, subject_type: str, subject_id: str,
                     subject_name: str = "", severity: str = "warning", detail: dict | None = None) -> tuple[Alert, bool]:
    """One open alert per (kind, subject). Returns (alert, newly_opened)."""
    cur = (await s.execute(select(Alert).where(
        Alert.kind == kind, Alert.subject_type == subject_type, Alert.subject_id == subject_id,
        Alert.resolved_at.is_(None)))).scalar_one_or_none()
    if cur is not None:
        return cur, False
    a = Alert(id=str(ULID()), kind=kind, subject_type=subject_type, subject_id=subject_id,
              subject_name=subject_name, severity=severity, opened_at=now, detail=detail, updated_at=now)
    s.add(a)
    await s.flush()
    return a, True


async def resolve_alerts(s: AsyncSession, now: int, kind: str, subject_type: str, subject_id: str) -> list[Alert]:
    rows = (await s.execute(select(Alert).where(
        Alert.kind == kind, Alert.subject_type == subject_type, Alert.subject_id == subject_id,
        Alert.resolved_at.is_(None)))).scalars().all()
    for a in rows:
        a.resolved_at = now
        a.updated_at = now
    return list(rows)


async def ack_alert(s: AsyncSession, now: int, alert_id: str, user_id: str) -> dict:
    a = await s.get(Alert, alert_id)
    if a is None:
        raise HubError("not_found", "Alert not found")
    if a.acked_at is None:
        a.acked_by, a.acked_at, a.updated_at = user_id, now, now
    return alert_view(a)
