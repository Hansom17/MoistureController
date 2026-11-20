"""Paged read requests (Gateway/specs.md 3.3 `query/*`)."""
import base64
import json

from sqlalchemy import func, select
from sqlalchemy.inspection import inspect

from mc_hub.bus.requests import Ctx, RequestHandler
from mc_hub.db.models import (Command, Device, DeviceEvent, HealthReport, Plant, Reading, Rule, RuleExecution)
from mc_hub.errors import HubError

from .commands import command_view
from .domain import _need

DEFAULT_LIMIT, MAX_LIMIT = 500, 2000
EXPORT_CHUNK = 1000


def enc(cur) -> str:
    return base64.urlsafe_b64encode(json.dumps(cur).encode()).decode()


def dec(cursor):
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:
        raise HubError("validation", detail="bad cursor")


def limit_of(b: dict, default=DEFAULT_LIMIT) -> int:
    n = int(b.get("limit", default))
    if not 1 <= n <= MAX_LIMIT:
        raise HubError("validation", detail=f"limit must be 1..{MAX_LIMIT}")
    return n


def row(o) -> dict:
    return {c.key: getattr(o, c.key) for c in inspect(o).mapper.column_attrs}


def _range(q, col, b):
    if b.get("from") is not None:
        q = q.where(col >= int(b["from"]))
    if b.get("to") is not None:
        q = q.where(col <= int(b["to"]))
    return q


EXPORT = {                       # part -> (model, order column, drop columns)
    "readings": (Reading, Reading.id), "health": (HealthReport, HealthReport.id),
    "events": (DeviceEvent, DeviceEvent.id), "rule_executions": (RuleExecution, RuleExecution.id),
}


def register(h: RequestHandler, snapshots) -> None:
    @h.register("query/readings")
    async def readings(ctx: Ctx, b: dict):
        _need(b, "plant_id")
        n, cur = limit_of(b), dec(b.get("cursor"))
        bucket = b.get("bucket", "raw")
        s = ctx.session
        if bucket == "raw":
            q = select(Reading).where(Reading.plant_id == b["plant_id"])
            q = _range(q, Reading.ts, b).order_by(Reading.ts, Reading.id)
            if cur:
                q = q.where((Reading.ts > cur[0]) | ((Reading.ts == cur[0]) & (Reading.id > cur[1])))
            rows = (await s.execute(q.limit(n + 1))).scalars().all()
            items = [{"ts": r.ts, "value": r.value, "raw": r.raw, "error": r.error, "slot": r.slot} for r in rows[:n]]
            nxt = enc([rows[n - 1].ts, rows[n - 1].id]) if len(rows) > n else None
            return {"items": items, "next_cursor": nxt}
        size = {"hour": 3600, "day": 86400}.get(bucket)
        if size is None:
            raise HubError("validation", detail="bucket must be raw, hour or day")
        t = (Reading.ts // size * size).label("t")
        q = select(t, func.avg(Reading.value), func.min(Reading.value), func.max(Reading.value), func.count(),
                   func.avg(Reading.raw)) \
            .where(Reading.plant_id == b["plant_id"], Reading.value.is_not(None))
        q = _range(q, Reading.ts, b).group_by(t).order_by(t)
        if cur:
            q = q.having(t > cur[0])
        rows = (await s.execute(q.limit(n + 1))).all()
        items = [{"ts": r[0], "avg": round(r[1], 2), "min": r[2], "max": r[3], "count": r[4],
                  "avg_raw": round(r[5], 1) if r[5] is not None else None} for r in rows[:n]]
        return {"items": items, "next_cursor": enc([rows[n - 1][0]]) if len(rows) > n else None}

    @h.register("query/commands")
    async def commands(ctx: Ctx, b: dict):
        n, cur = limit_of(b, 100), dec(b.get("cursor"))
        q = select(Command)
        for key, col in (("plant_id", Command.plant_id), ("device_id", Command.device_id), ("status", Command.status)):
            if b.get(key):
                q = q.where(col == b[key])
        q = q.order_by(Command.created_at.desc(), Command.id.desc())
        if cur:
            q = q.where((Command.created_at < cur[0]) | ((Command.created_at == cur[0]) & (Command.id < cur[1])))
        rows = (await ctx.session.execute(q.limit(n + 1))).scalars().all()
        return {"items": [command_view(c) for c in rows[:n]],
                "next_cursor": enc([rows[n - 1].created_at, rows[n - 1].id]) if len(rows) > n else None}

    @h.register("query/command")
    async def command(ctx: Ctx, b: dict):
        _need(b, "command_id")
        c = await ctx.session.get(Command, b["command_id"])
        if c is None:
            raise HubError("not_found", "Command not found")
        return {"command": command_view(c)}

    async def _by_device(ctx: Ctx, b: dict, model, rangecol, fmt):
        _need(b, "device_id")
        n, cur = limit_of(b, 200), dec(b.get("cursor"))
        q = select(model).where(model.device_id == b["device_id"])
        q = _range(q, rangecol, b).order_by(rangecol.desc(), model.id.desc())
        if cur:
            q = q.where((rangecol < cur[0]) | ((rangecol == cur[0]) & (model.id < cur[1])))
        rows = (await ctx.session.execute(q.limit(n + 1))).scalars().all()
        return {"items": [fmt(r) for r in rows[:n]],
                "next_cursor": enc([rows[n - 1].ts, rows[n - 1].id]) if len(rows) > n else None}

    @h.register("query/device_health")
    async def device_health(ctx: Ctx, b: dict):
        return await _by_device(ctx, b, HealthReport, HealthReport.ts, lambda r: {
            "ts": r.ts, "voltage_mv": r.voltage_mv, "link_quality": r.link_quality, "diagnostics": r.diagnostics})

    @h.register("query/device_events")
    async def device_events(ctx: Ctx, b: dict):
        return await _by_device(ctx, b, DeviceEvent, DeviceEvent.ts, lambda r: {
            "ts": r.ts, "code": r.code, "slot": r.slot, "arg": r.arg})

    @h.register("query/rule_executions")
    async def rule_executions(ctx: Ctx, b: dict):
        _need(b, "rule_id")
        n, cur = limit_of(b, 100), dec(b.get("cursor"))
        q = select(RuleExecution).where(RuleExecution.rule_id == b["rule_id"]).order_by(RuleExecution.id.desc())
        if cur:
            q = q.where(RuleExecution.id < cur[0])
        rows = (await ctx.session.execute(q.limit(n + 1))).scalars().all()
        return {"items": [{"ts": r.ts, "decision": r.decision, "skip_reason": r.skip_reason,
                           "command_id": r.command_id, "reading_ref": r.reading_ref} for r in rows[:n]],
                "next_cursor": enc([rows[n - 1].id]) if len(rows) > n else None}

    @h.register("query/export")
    async def export(ctx: Ctx, b: dict):
        _need(b, "part")
        part, s = b["part"], ctx.session
        if part == "installation":
            return {"items": [await snapshots.build(s, "installation")], "next_cursor": None}
        small = {"devices": Device, "plants": Plant, "rules": Rule}
        if part in small:
            rows = (await s.execute(select(small[part]))).scalars().all()
            return {"items": [row(r) for r in rows], "next_cursor": None}
        if part == "commands":
            model, col = Command, Command.id
        elif part in EXPORT:
            model, col = EXPORT[part]
        else:
            raise HubError("validation", detail="unknown export part")
        cur = dec(b.get("cursor"))
        q = select(model).order_by(col)
        if cur:
            q = q.where(col > cur[0])
        rows = (await s.execute(q.limit(EXPORT_CHUNK + 1))).scalars().all()
        last = getattr(rows[EXPORT_CHUNK - 1], col.key) if len(rows) > EXPORT_CHUNK else None
        return {"items": [row(r) for r in rows[:EXPORT_CHUNK]], "next_cursor": enc([last]) if last is not None else None}
