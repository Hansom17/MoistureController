"""Device configuration revisions (Gateway/specs.md section 10)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mc_hub.db.models import ConfigRevision, Device
from mc_hub.errors import HubError

from . import alerts, boards
from .effects import Effects
from .views import alert_view

DEFAULTS = {"report_interval_s": 300, "fast_report_interval_s": 30, "fast_report_hold_s": 120, "batt_low_mv": 3500}
MODULES = ("moisture", "pump")


def _int(v, name, lo, hi):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise HubError("validation", detail=f"{name} must be an integer {lo}..{hi}")
    return v


def validate(body: dict, board: dict) -> dict:
    """Returns the normalized configuration (without `rev`); raises validation errors."""
    cfg = {k: _int(body.get(k, dflt), k, lo, hi) for k, dflt, lo, hi in (
        ("report_interval_s", 300, 10, 3600), ("fast_report_interval_s", 30, 10, 300),
        ("fast_report_hold_s", 120, 0, 1800), ("batt_low_mv", 3500, 2500, 5000))}
    ports = {p["id"]: p for p in board["ports"]}
    used_slots: set[int] = set()
    used_ports: set[str] = set()
    slots = []
    for sl in body.get("slots", []):
        n = _int(sl.get("slot"), "slot", 0, 5)
        if n in used_slots:
            raise HubError("validation", detail=f"slot {n} appears twice")
        used_slots.add(n)
        module = sl.get("module")
        if module == "empty":
            continue
        if module not in MODULES:
            raise HubError("validation", detail=f"slot {n}: module must be one of {list(MODULES) + ['empty']}")
        port = sl.get("port")
        if port not in ports:
            raise HubError("validation", detail=f"slot {n}: port {port!r} does not exist on {board['name']}")
        if module not in ports[port]["roles"]:
            raise HubError("validation", detail=f"slot {n}: port {port} cannot be a {module}")
        if port in used_ports:
            raise HubError("validation", detail=f"slot {n}: port {port} is used by another slot")
        used_ports.add(port)
        out = {"slot": n, "module": module, "port": port}
        if module == "moisture":
            out["cal_dry"] = _int(sl.get("cal_dry", 3000), f"slot {n} cal_dry", 0, 4095)
            out["cal_wet"] = _int(sl.get("cal_wet", 1200), f"slot {n} cal_wet", 0, 4095)
            if out["cal_dry"] == out["cal_wet"]:
                raise HubError("validation", detail=f"slot {n}: cal_dry and cal_wet must differ")
            out["samples"] = _int(sl.get("samples", 16), f"slot {n} samples", 1, 64)
        else:
            out["max_run_s"] = _int(sl.get("max_run_s", 60), f"slot {n} max_run_s", 1, 600)
            out["min_pause_s"] = _int(sl.get("min_pause_s", 600), f"slot {n} min_pause_s", 0, 86400)
            out["active_high"] = bool(sl.get("active_high", True))
        slots.append(out)
    cfg["slots"] = sorted(slots, key=lambda x: x["slot"])
    return cfg


async def put(s: AsyncSession, fx: Effects, now: int, d: Device | None, base_rev: int, body: dict,
              created_by: str | None) -> int:
    if d is None or d.deleted_at is not None:
        raise HubError("not_found", "Device not found")
    if d.status in ("joining", "join_failed", "unsupported"):
        raise HubError("device_not_ready", detail=f"device is {d.status}")
    board = boards.get(d.board)
    if board is None:
        raise HubError("device_not_ready", detail="the device has not reported a known board yet")
    if base_rev != d.desired_rev:
        raise HubError("conflict", "Configuration changed meanwhile", f"current revision is {d.desired_rev}")
    cfg = validate(body, board)
    d.desired_rev += 1
    cfg = {"rev": d.desired_rev, **cfg}
    d.desired_config = cfg
    d.rejected_rev = None
    d.config_error = None
    d.updated_at = now
    s.add(ConfigRevision(device_id=d.id, rev=d.desired_rev, kind="desired", body=cfg, created_at=now,
                         created_by=created_by))
    fx.kick(d.id)
    fx.touch("devices")
    return d.desired_rev


def initial(d: Device, now: int, s: AsyncSession) -> None:
    """Revision 1 for a new device: no slots, default intervals."""
    cfg = {"rev": 1, **DEFAULTS, "slots": []}
    d.desired_rev, d.desired_config = 1, cfg
    s.add(ConfigRevision(device_id=d.id, rev=1, kind="initial", body=cfg, created_at=now))


async def apply_state(s: AsyncSession, fx: Effects, now: int, d: Device, cfg_rev: int, result: str | None,
                      error) -> None:
    """The device reported its configuration state."""
    d.reported_rev = cfg_rev
    rev = await s.get(ConfigRevision, (d.id, cfg_rev))
    d.reported_config = rev.body if rev is not None else None
    if rev is not None and rev.confirmed_at is None and result == "ok":
        rev.confirmed_at, rev.result = now, "ok"
    if result == "rejected" and d.desired_rev > cfg_rev:
        d.rejected_rev = d.desired_rev
        d.config_error = {"raw": error}
        pending = await s.get(ConfigRevision, (d.id, d.desired_rev))
        if pending is not None:
            pending.result, pending.error = "rejected", {"raw": error}
        a, new = await alerts.open_alert(s, now, "config_rejected", "device", d.id, d.name or d.id,
                                         detail={"rev": d.desired_rev, "error": error})
        if new:
            fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
            fx.notify(f"{d.name or d.id}: configuration rejected", [], "alert", alert_kind="config_rejected")
    elif d.reported_rev == d.desired_rev:
        d.config_error = None
        for a in await alerts.resolve_alerts(s, now, "config_rejected", "device", d.id):
            fx.emit("alert", alert_view(a)); fx.touch("alerts_open")
    fx.kick(d.id)
