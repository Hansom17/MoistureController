"""Row -> JSON shapes shared by events and snapshots (Gateway/mqtt-contract.yaml)."""
from mc_hub.db.models import Alert, Device, Plant, Rule

from . import battery


def device_view(d: Device, now: int | None = None) -> dict:
    return {
        "id": d.id, "ieee": d.ieee, "name": d.name, "model": d.model, "fw": d.fw, "board": d.board,
        "status": d.status, "safe_reason": d.safe_reason, "last_seen_at": d.last_seen_at,
        "link_quality": d.link_quality, "voltage_mv": d.voltage_mv, "battery": battery.view(d, now),
        "config_sync": config_sync(d), "desired_rev": d.desired_rev, "reported_rev": d.reported_rev,
        "latest_readings": d.slots or {}, "diagnostics": d.diagnostics or {},
        "desired_config": d.desired_config, "reported_config": d.reported_config, "config_error": d.config_error,
        "updated_at": d.updated_at, "deleted": d.deleted_at is not None,
    }


def config_sync(d: Device) -> str:
    if d.rejected_rev is not None and d.rejected_rev >= d.desired_rev > 0:
        return "rejected"
    if d.desired_rev == 0 or d.reported_rev == d.desired_rev:
        return "in_sync"
    return "pending"


def plant_view(p: Plant, latest: dict | None = None, trend: str = "steady") -> dict:
    latest = latest or {}
    return {
        "id": p.id, "name": p.name, "notes": p.notes,
        "sensor": {"device_id": p.sensor_device_id, "slot": p.sensor_slot},
        "pump": {"device_id": p.pump_device_id, "slot": p.pump_slot},
        "latest_value": latest.get("value"), "latest_ts": latest.get("ts"), "trend": trend,
        "archived": p.archived_at is not None, "updated_at": p.updated_at,
    }


def rule_view(r: Rule) -> dict:
    return {
        "id": r.id, "plant_id": r.plant_id, "enabled": r.enabled, "threshold": r.threshold,
        "water_s": r.water_s, "cooldown_s": r.cooldown_s, "max_per_day": r.max_per_day,
        "quiet_from": r.quiet_from, "quiet_to": r.quiet_to,
        "notify_channels": r.notify_channels, "notify_on": r.notify_on, "updated_at": r.updated_at,
    }


def alert_view(a: Alert) -> dict:
    return {
        "id": a.id, "kind": a.kind, "subject": {"type": a.subject_type, "id": a.subject_id, "name": a.subject_name},
        "severity": a.severity, "opened_at": a.opened_at, "resolved_at": a.resolved_at,
        "acked_by": a.acked_by, "acked_at": a.acked_at, "detail": a.detail, "updated_at": a.updated_at,
    }
