"""Owner data export as ZIP (Api_Specs §12). No keys are ever exported."""

import gzip
import hashlib
import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Response
from sqlalchemy import select

from ..auth.deps import OwnerSensitive
from ..db.models import (
    CommandRow,
    Device,
    DeviceEvent,
    HealthReport,
    Membership,
    Plant,
    ReadingRow,
    Rule,
    User,
)
from ..db.types import utcnow
from ..services.common import audit

router = APIRouter(tags=["export"])
FORMAT_VERSION = 1


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


def _row(obj, skip=()) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in skip}


@router.post("/households/{household_id}/export", response_class=Response,
             responses={200: {"content": {"application/zip": {}}}})
async def export(h: OwnerSensitive):
    s = h.uow.s
    hid = h.id
    devices = list(await s.scalars(select(Device).where(Device.household_id == hid)))
    device_ids = [d.id for d in devices]
    files: dict[str, bytes] = {}
    counts: dict[str, int] = {}

    def put_json(name: str, data) -> None:
        files[name] = json.dumps(data, default=_default, indent=2).encode()
        counts[name] = len(data) if isinstance(data, list) else 1

    def put_ndjson(name: str, rows: list[dict]) -> None:
        body = "\n".join(json.dumps(r, default=_default) for r in rows).encode()
        files[name] = gzip.compress(body)
        counts[name] = len(rows)

    put_json("household.json", _row(h.household, skip=("snapshot_rev", "keys_rev")))
    members = await s.execute(select(Membership, User).join(User, User.uid == Membership.user_uid)
                              .where(Membership.household_id == hid))
    put_json("members.json", [{"display_name": u.display_name, "role": m.role,
                               "joined_at": m.created_at} for m, u in members])
    put_json("devices.json", [_row(d, skip=("psk_enc",)) for d in devices])
    put_json("plants.json", [_row(p) for p in await s.scalars(
        select(Plant).where(Plant.household_id == hid))])
    put_json("rules.json", [_row(r) for r in await s.scalars(
        select(Rule).where(Rule.household_id == hid))])
    for name, model in (("readings", ReadingRow), ("health", HealthReport),
                        ("events", DeviceEvent)):
        rows = await s.scalars(select(model).where(model.device_id.in_(device_ids))
                               .order_by(model.id)) if device_ids else []
        put_ndjson(f"{name}.ndjson.gz", [_row(r) for r in rows])
    put_ndjson("commands.ndjson.gz", [_row(c) for c in await s.scalars(
        select(CommandRow).where(CommandRow.household_id == hid).order_by(CommandRow.created_at))])

    manifest = {
        "format": "moisturecontroller-export", "version": FORMAT_VERSION,
        "exported_at": utcnow().isoformat(), "counts": counts,
        "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, data in files.items():
            z.writestr(name, data)
    audit(h.uow, hid, h.user.uid, "household.export")
    await h.uow.commit()
    filename = f"moisturecontroller-{hid}-{utcnow():%Y%m%d}.zip"
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
