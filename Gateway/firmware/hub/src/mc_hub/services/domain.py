"""Request handlers for installation, plants, rules, alerts and device names (slice 1)."""
import re

from sqlalchemy import select
from ulid import ULID

from mc_hub.bus.requests import Ctx, RequestHandler
from mc_hub.db.models import Device, Plant, Rule, Setting
from mc_hub.errors import HubError
from mc_hub.params import CONFIG

from . import alerts, battery, config_sync
from .views import alert_view, device_view, plant_view, rule_view

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_WATER_S = 300     # hub hard limit; the module enforces its own max_run_s as well
SLOTS = range(0, 6)


def _need(body: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in body]
    if missing:
        raise HubError("validation", detail="missing: " + ", ".join(missing))


async def _set(s, key: str, value) -> None:
    row = await s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


async def _slot_ref(ctx: Ctx, ref: dict | None, what: str) -> tuple[str | None, int | None]:
    if not ref or ref.get("device_id") is None:
        return None, None
    dev = await ctx.session.get(Device, ref["device_id"])
    slot = ref.get("slot")
    if dev is None or dev.deleted_at is not None:
        raise HubError("validation", detail=f"{what}: unknown device")
    if slot not in SLOTS:
        raise HubError("validation", detail=f"{what}: slot must be 0..5")
    return dev.id, slot


def register(h: RequestHandler) -> None:
    @h.register("installation_set")
    async def installation_set(ctx: Ctx, b: dict):
        s = ctx.session
        if "name" in b:
            await _set(s, "name", str(b["name"]))
        if "timezone" in b:
            await _set(s, "timezone", str(b["timezone"]))
        if "battery_low_mv" in b or "battery_critical_mv" in b:
            cur_low = await s.get(Setting, "battery_low_mv")
            cur_crit = await s.get(Setting, "battery_critical_mv")
            low = int(b.get("battery_low_mv", cur_low.value if cur_low else battery.DEFAULT_LOW_MV))
            crit = int(b.get("battery_critical_mv", cur_crit.value if cur_crit else battery.DEFAULT_CRITICAL_MV))
            lo_mv, hi_mv = CONFIG["batt_critical_mv"]["min"], CONFIG["batt_low_mv"]["max"]
            if not lo_mv <= crit < low <= hi_mv:
                raise HubError("validation", detail=f"battery thresholds must satisfy {lo_mv} <= critical < low <= {hi_mv} mV")
            await _set(s, "battery_low_mv", low)
            await _set(s, "battery_critical_mv", crit)
            await config_sync.push_battery(s, ctx.fx, ctx.now, low, crit, ctx.actor.user_id)
        if "telegram" in b:
            cur = (await s.get(Setting, "telegram"))
            old = dict(cur.value) if cur and cur.value else {}
            new = dict(b["telegram"])
            if not new.get("token"):          # the token is write-only: empty keeps the old one
                new["token"] = old.get("token")
            await _set(s, "telegram", new)
        ctx.touch("installation")
        ctx.emit("installation", {"updated_at": ctx.now})
        return {}

    @h.register("plant_create")
    async def plant_create(ctx: Ctx, b: dict):
        _need(b, "name")
        if not str(b["name"]).strip():
            raise HubError("validation", detail="name is empty")
        sd, ss = await _slot_ref(ctx, b.get("sensor"), "sensor")
        pd, ps = await _slot_ref(ctx, b.get("pump"), "pump")
        p = Plant(id=str(ULID()), name=str(b["name"]).strip(), notes=str(b.get("notes", "")),
                  sensor_device_id=sd, sensor_slot=ss, pump_device_id=pd, pump_slot=ps,
                  created_at=ctx.now, updated_at=ctx.now)
        ctx.session.add(p)
        ctx.touch("plants")
        ctx.emit("plant", plant_view(p))
        return {"plant": plant_view(p)}

    @h.register("plant_update")
    async def plant_update(ctx: Ctx, b: dict):
        _need(b, "plant_id", "fields")
        p = await ctx.session.get(Plant, b["plant_id"])
        if p is None or p.archived_at is not None:
            raise HubError("not_found", "Plant not found")
        f = b["fields"]
        if "name" in f:
            p.name = str(f["name"]).strip() or p.name
        if "notes" in f:
            p.notes = str(f["notes"])
        if "sensor" in f:
            p.sensor_device_id, p.sensor_slot = await _slot_ref(ctx, f["sensor"], "sensor")
        if "pump" in f:
            p.pump_device_id, p.pump_slot = await _slot_ref(ctx, f["pump"], "pump")
        p.updated_at = ctx.now
        ctx.touch("plants")
        ctx.emit("plant", plant_view(p))
        return {"plant": plant_view(p)}

    @h.register("plant_delete")
    async def plant_delete(ctx: Ctx, b: dict):
        _need(b, "plant_id")
        p = await ctx.session.get(Plant, b["plant_id"])
        if p is None or p.archived_at is not None:
            raise HubError("not_found", "Plant not found")
        p.archived_at = p.updated_at = ctx.now       # history is kept
        rules = (await ctx.session.execute(select(Rule).where(Rule.plant_id == p.id, Rule.deleted_at.is_(None)))).scalars().all()
        for r in rules:
            r.enabled = False
            r.updated_at = ctx.now
        ctx.touch("plants", "rules")
        ctx.emit("plant", plant_view(p))
        return {}

    def _check_rule(f: dict) -> None:
        if "threshold" in f and not 0 <= int(f["threshold"]) <= 100:
            raise HubError("validation", detail="threshold must be 0..100")
        if "water_s" in f and not 1 <= int(f["water_s"]) <= MAX_WATER_S:
            raise HubError("safety_limit", detail=f"water_s must be 1..{MAX_WATER_S}")
        if "cooldown_s" in f and int(f["cooldown_s"]) < 0:
            raise HubError("validation", detail="cooldown_s must be >= 0")
        if "max_per_day" in f and not 1 <= int(f["max_per_day"]) <= 24:
            raise HubError("validation", detail="max_per_day must be 1..24")
        for k in ("quiet_from", "quiet_to"):
            if f.get(k) is not None and not HHMM.match(str(f[k])):
                raise HubError("validation", detail=f"{k} must be HH:MM")
        if (f.get("quiet_from") is None) != (f.get("quiet_to") is None) and ("quiet_from" in f and "quiet_to" in f):
            raise HubError("validation", detail="quiet_from and quiet_to go together")
        for k, allowed in (("notify_channels", {"app", "telegram"}), ("notify_on", {"watered", "skipped_problem", "failed"})):
            if k in f and not (isinstance(f[k], list) and set(f[k]) <= allowed):
                raise HubError("validation", detail=f"{k} must be a subset of {sorted(allowed)}")

    @h.register("rule_create")
    async def rule_create(ctx: Ctx, b: dict):
        _need(b, "plant_id", "threshold", "water_s", "cooldown_s", "max_per_day")
        p = await ctx.session.get(Plant, b["plant_id"])
        if p is None or p.archived_at is not None:
            raise HubError("not_found", "Plant not found")
        if p.pump_device_id is None:
            raise HubError("conflict", "The plant has no pump", "Assign a pump first.")
        _check_rule(b)
        r = Rule(id=str(ULID()), plant_id=p.id, enabled=bool(b.get("enabled", True)),
                 threshold=int(b["threshold"]), water_s=int(b["water_s"]), cooldown_s=int(b["cooldown_s"]),
                 max_per_day=int(b["max_per_day"]), quiet_from=b.get("quiet_from"), quiet_to=b.get("quiet_to"),
                 notify_channels=b.get("notify_channels", ["app"]), notify_on=b.get("notify_on", ["failed"]),
                 created_by=ctx.actor.user_id, updated_at=ctx.now)
        ctx.session.add(r)
        ctx.touch("rules")
        ctx.emit("rule", rule_view(r))
        return {"rule": rule_view(r)}

    @h.register("rule_update")
    async def rule_update(ctx: Ctx, b: dict):
        _need(b, "rule_id", "fields")
        r = await ctx.session.get(Rule, b["rule_id"])
        if r is None or r.deleted_at is not None:
            raise HubError("not_found", "Rule not found")
        f = b["fields"]
        _check_rule(f)
        for k in ("enabled", "threshold", "water_s", "cooldown_s", "max_per_day", "quiet_from", "quiet_to",
                  "notify_channels", "notify_on"):
            if k in f:
                setattr(r, k, f[k])
        r.updated_at = ctx.now
        ctx.touch("rules")
        ctx.emit("rule", rule_view(r))
        return {"rule": rule_view(r)}

    @h.register("rule_delete")
    async def rule_delete(ctx: Ctx, b: dict):
        _need(b, "rule_id")
        r = await ctx.session.get(Rule, b["rule_id"])
        if r is None or r.deleted_at is not None:
            raise HubError("not_found", "Rule not found")
        r.enabled = False
        r.deleted_at = r.updated_at = ctx.now      # the row stays for the execution history
        view = rule_view(r) | {"deleted": True}
        ctx.touch("rules")
        ctx.emit("rule", view)
        return {}

    @h.register("alert_ack")
    async def alert_ack(ctx: Ctx, b: dict):
        _need(b, "alert_id")
        view = await alerts.ack_alert(ctx.session, ctx.now, b["alert_id"], ctx.actor.user_id)
        ctx.touch("alerts_open")
        ctx.emit("alert", view)
        return {"alert": view}

    @h.register("device_update")
    async def device_update(ctx: Ctx, b: dict):
        _need(b, "device_id", "name")
        d = await ctx.session.get(Device, b["device_id"])
        if d is None or d.deleted_at is not None:
            raise HubError("not_found", "Device not found")
        name = str(b["name"]).strip()
        if not name:
            raise HubError("validation", detail="name is empty")
        d.name, d.updated_at = name, ctx.now
        ctx.touch("devices")
        ctx.emit("device", device_view(d))
        return {"device": device_view(d)}
