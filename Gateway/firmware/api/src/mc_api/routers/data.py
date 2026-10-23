"""Export and backup (Gateway/specs.md section 14)."""
import gzip
import io
import json
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from mc_api import __version__
from mc_api.auth import Principal, app_of, audit, reauth, require
from mc_api.convert import iso
from mc_api.db.models import User

router = APIRouter()
PARTS = [("installation", "installation.json", False), ("devices", "devices.json", False),
         ("plants", "plants.json", False), ("rules", "rules.json", False),
         ("readings", "readings.ndjson.gz", True), ("health", "health.ndjson.gz", True),
         ("events", "events.ndjson.gz", True), ("commands", "commands.ndjson.gz", True),
         ("rule_executions", "rule_executions.ndjson.gz", True)]


@router.post("/export")
async def export(request: Request, p: Principal = Depends(require("owner"))):
    app = app_of(request)
    reauth(request, p)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"format": 1, "api": __version__,
                                                "created_at": iso(int(app.clock.now())),
                                                "parts": [name for _, name, _ in PARTS] + ["users.json"]}, indent=2))
        async with app.sessions() as s:                      # users stay here and carry no hashes
            users = [{"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
                      "created_at": iso(u.created_at), "disabled": u.disabled_at is not None}
                     for u in (await s.execute(select(User))).scalars()]
        z.writestr("users.json", json.dumps(users, indent=2))
        for part, name, paged in PARTS:
            items, cursor = [], None
            while True:
                r = await app.hub.request("query/export", {"part": part, **({"cursor": cursor} if cursor else {})},
                                          p.actor, timeout=30)
                items += r["items"]
                cursor = r.get("next_cursor")
                if not cursor:
                    break
            if paged:
                z.writestr(name, gzip.compress("\n".join(json.dumps(i) for i in items).encode()))
            else:
                z.writestr(name, json.dumps(items[0] if part == "installation" and items else items, indent=2))
    await audit(app, p.user_id, "export", None, request)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="moisture-export.zip"'})


@router.post("/backup")
async def backup(request: Request, p: Principal = Depends(require("admin"))):
    app = app_of(request)
    hub_part = await app.hub.request("backup", {}, p.actor, timeout=60)
    api_part = None
    if app.engine is not None:
        from .backup import backup_api_db
        api_part = await backup_api_db(app)
    await audit(app, p.user_id, "backup", None, request)
    return {"hub": hub_part, "api": api_part}
