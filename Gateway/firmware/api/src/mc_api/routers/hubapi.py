"""Endpoints that read the hub's snapshots or turn into hub requests (Gateway/specs.md section 6)."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from mc_api import __version__
from mc_api.auth import Principal, app_of, audit, reauth, rank, require
from mc_api.convert import to_api, to_unix
from mc_api.errors import ApiError

router = APIRouter()


def snap(request: Request, name: str, default=None):
    """A hub snapshot, marked stale when the hub is not reachable."""
    return app_of(request).hub.state.get(name, default)


async def hub(request: Request, p: Principal, kind: str, body: dict | None = None, **kw) -> dict:
    return to_api(await app_of(request).hub.request(kind, body or {}, p.actor, **kw))


def find(items: list, id: str, what: str) -> dict:
    for it in items:
        if it["id"] == id:
            return it
    raise ApiError("not_found", f"{what} not found")


def stale(request: Request) -> bool:
    return not app_of(request).hub.online


# ---- installation, status, boards ---------------------------------------------------------------------

@router.get("/installation")
async def get_installation(request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(snap(request, "installation", {})) | {"stale": stale(request)}


class TelegramIn(BaseModel):
    token: str | None = None
    chat_id: str | None = None
    kinds: list[str] | None = None


class InstallationIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = None
    battery_low_mv: int | None = None
    battery_critical_mv: int | None = None
    telegram: TelegramIn | None = None


@router.patch("/installation")
async def patch_installation(body: InstallationIn, request: Request, p: Principal = Depends(require("owner"))):
    if body.timezone:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise ApiError("validation", detail="timezone is not a known IANA zone")
    data = body.model_dump(exclude_none=True)
    if "telegram" in data:
        data["telegram"] = {k: v for k, v in data["telegram"].items() if v is not None}
    await hub(request, p, "installation_set", data)
    await audit(app_of(request), p.user_id, "installation_changed", {k: ("***" if k == "telegram" else v)
                                                                      for k, v in data.items()}, request)
    return to_api(snap(request, "installation", {}))


@router.get("/status")
async def get_status(request: Request, p: Principal = Depends(require("viewer"))):
    app = app_of(request)
    import os
    size = None
    try:
        size = os.path.getsize(app.settings.db_path)
    except OSError:
        pass
    return {"api": {"version": __version__, "db_size": size},
            "hub": {"online": app.hub.online, "compatible": app.hub.compatible,
                    **(app.hub.hub_status or {})},
            "gateway": to_api(snap(request, "status", {}))}


@router.get("/meta/boards/{board}")
async def get_board(board: str, request: Request, p: Principal = Depends(require("viewer"))):
    for b in snap(request, "boards", []):
        if b.get("name") == board:
            return b
    raise ApiError("not_found", "Unknown board")


# ---- devices ------------------------------------------------------------------------------------------

@router.get("/devices")
async def list_devices(request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(snap(request, "devices", []))


class JoinIn(BaseModel):
    install_code: str | None = None
    seconds: int = 120


@router.post("/devices/join", status_code=202)
async def join_open(body: JoinIn, request: Request, p: Principal = Depends(require("admin"))):
    r = await hub(request, p, "device_join_open", body.model_dump(exclude_none=True))
    await audit(app_of(request), p.user_id, "join_opened", {"seconds": body.seconds}, request)
    return r["join"]


@router.get("/devices/join")
async def join_state(request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(snap(request, "join", {"open": False, "devices": []}))


@router.delete("/devices/join", status_code=204)
async def join_close(request: Request, p: Principal = Depends(require("admin"))):
    await hub(request, p, "device_join_close")


@router.get("/devices/{device_id}")
async def get_device(device_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(find(snap(request, "devices", []), device_id, "Device"))


class DevicePatch(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.patch("/devices/{device_id}")
async def patch_device(device_id: str, body: DevicePatch, request: Request, p: Principal = Depends(require("admin"))):
    return (await hub(request, p, "device_update", {"device_id": device_id, "name": body.name}))["device"]


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, request: Request, force: bool = False,
                        p: Principal = Depends(require("admin"))):
    reauth(request, p)
    await hub(request, p, "device_remove", {"device_id": device_id, "force": force})
    await audit(app_of(request), p.user_id, "device_removed", {"device": device_id, "force": force}, request)


@router.get("/devices/{device_id}/config")
async def get_config(device_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    d = find(snap(request, "devices", []), device_id, "Device")
    return {"desired_rev": d["desired_rev"], "reported_rev": d["reported_rev"], "sync_state": d["config_sync"],
            "desired": d.get("desired_config"), "reported": d.get("reported_config"), "error": d.get("config_error"),
            "board": d.get("board")}


class ConfigIn(BaseModel):
    base_rev: int
    config: dict


@router.put("/devices/{device_id}/config")
async def put_config(device_id: str, body: ConfigIn, request: Request, p: Principal = Depends(require("admin"))):
    r = await hub(request, p, "device_config_put", {"device_id": device_id, "base_rev": body.base_rev,
                                                    "config": body.config})
    await audit(app_of(request), p.user_id, "device_config", {"device": device_id, "rev": r["rev"]}, request)
    return r


def paging(request: Request, **extra) -> dict:
    q = dict(request.query_params)
    out = {k: v for k, v in extra.items() if v is not None}
    if "limit" in q:
        out["limit"] = int(q["limit"])
    if "cursor" in q:
        out["cursor"] = q["cursor"]
    return out


@router.get("/devices/{device_id}/health")
async def device_health(device_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    q = request.query_params
    return await hub(request, p, "query/device_health", paging(request, device_id=device_id,
                     **{"from": to_unix(q.get("from")), "to": to_unix(q.get("to"))}))


@router.get("/devices/{device_id}/events")
async def device_events(device_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return await hub(request, p, "query/device_events", paging(request, device_id=device_id))


class ActionIn(BaseModel):
    action: str


class CalibrateIn(BaseModel):
    measured_mv: int = Field(ge=1000, le=6000)


@router.post("/devices/{device_id}/battery/calibrate")
async def calibrate_battery(device_id: str, body: CalibrateIn, request: Request,
                            p: Principal = Depends(require("admin"))):
    r = await hub(request, p, "device_battery_calibrate", {"device_id": device_id, "measured_mv": body.measured_mv})
    await audit(app_of(request), p.user_id, "battery_calibrated", {"device": device_id, "measured_mv": body.measured_mv,
                                                                    "cal_permille": r["cal_permille"]}, request)
    return r


@router.post("/devices/{device_id}/actions", status_code=202)
async def device_action(device_id: str, body: ActionIn, request: Request, p: Principal = Depends(require("member"))):
    if body.action != "identify" and rank(p.role) < rank("admin"):
        raise ApiError("forbidden", "Only admins can reboot a device or clear its safe mode")
    return (await hub(request, p, "device_action", {"device_id": device_id, "action": body.action}))["command"]


# ---- plants, readings, commands --------------------------------------------------------------------------

@router.get("/plants")
async def list_plants(request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(snap(request, "plants", []))


class SlotRef(BaseModel):
    device_id: str | None = None
    slot: int | None = None


class PlantIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    notes: str = ""
    sensor: SlotRef | None = None
    pump: SlotRef | None = None


@router.post("/plants", status_code=201)
async def create_plant(body: PlantIn, request: Request, p: Principal = Depends(require("member"))):
    return (await hub(request, p, "plant_create", body.model_dump(exclude_none=True)))["plant"]


@router.get("/plants/{plant_id}")
async def get_plant(plant_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(find(snap(request, "plants", []), plant_id, "Plant"))


class PlantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    notes: str | None = None
    sensor: SlotRef | None = None
    pump: SlotRef | None = None


@router.patch("/plants/{plant_id}")
async def patch_plant(plant_id: str, body: PlantPatch, request: Request, p: Principal = Depends(require("member"))):
    fields = body.model_dump(exclude_unset=True)
    return (await hub(request, p, "plant_update", {"plant_id": plant_id, "fields": fields}))["plant"]


@router.delete("/plants/{plant_id}", status_code=204)
async def delete_plant(plant_id: str, request: Request, p: Principal = Depends(require("member"))):
    await hub(request, p, "plant_delete", {"plant_id": plant_id})


@router.get("/plants/{plant_id}/readings")
async def plant_readings(plant_id: str, request: Request, bucket: str = "raw",
                         p: Principal = Depends(require("viewer"))):
    q = request.query_params
    return await hub(request, p, "query/readings", paging(
        request, plant_id=plant_id, bucket=bucket, **{"from": to_unix(q.get("from")), "to": to_unix(q.get("to"))}))


@router.get("/plants/{plant_id}/commands")
async def plant_commands(plant_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return await hub(request, p, "query/commands", paging(request, plant_id=plant_id))


class WaterIn(BaseModel):
    seconds: int
    ttl_s: int | None = None


@router.post("/plants/{plant_id}/water", status_code=202)
async def water(plant_id: str, body: WaterIn, request: Request, p: Principal = Depends(require("member"))):
    r = await hub(request, p, "water", {"plant_id": plant_id, **body.model_dump(exclude_none=True)})
    await audit(app_of(request), p.user_id, "water", {"plant": plant_id, "seconds": body.seconds}, request)
    return r["command"]


@router.get("/commands")
async def list_commands(request: Request, plant_id: str | None = None, device_id: str | None = None,
                        status: str | None = None, p: Principal = Depends(require("viewer"))):
    return await hub(request, p, "query/commands", paging(request, plant_id=plant_id, device_id=device_id,
                                                          status=status))


@router.get("/commands/{command_id}")
async def get_command(command_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return (await hub(request, p, "query/command", {"command_id": command_id}))["command"]


@router.post("/commands/{command_id}/cancel", status_code=202)
async def cancel_command(command_id: str, request: Request, p: Principal = Depends(require("member"))):
    return (await hub(request, p, "command_cancel", {"command_id": command_id}))["command"]


# ---- rules, alerts --------------------------------------------------------------------------------------------

class RuleIn(BaseModel):
    threshold: int
    water_s: int
    cooldown_s: int
    max_per_day: int
    quiet_from: str | None = None
    quiet_to: str | None = None
    enabled: bool = True
    notify_channels: list[str] = ["app"]
    notify_on: list[str] = ["failed"]


class RulePatch(BaseModel):
    threshold: int | None = None
    water_s: int | None = None
    cooldown_s: int | None = None
    max_per_day: int | None = None
    quiet_from: str | None = None
    quiet_to: str | None = None
    enabled: bool | None = None
    notify_channels: list[str] | None = None
    notify_on: list[str] | None = None


@router.get("/plants/{plant_id}/rules")
async def list_rules(plant_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return to_api([r for r in snap(request, "rules", []) if r["plant_id"] == plant_id])


@router.post("/plants/{plant_id}/rules", status_code=201)
async def create_rule(plant_id: str, body: RuleIn, request: Request, p: Principal = Depends(require("member"))):
    return (await hub(request, p, "rule_create", {"plant_id": plant_id, **body.model_dump()}))["rule"]


@router.patch("/plants/{plant_id}/rules/{rule_id}")
async def patch_rule(plant_id: str, rule_id: str, body: RulePatch, request: Request,
                     p: Principal = Depends(require("member"))):
    own = [r for r in snap(request, "rules", []) if r["plant_id"] == plant_id and r["id"] == rule_id]
    if not own and app_of(request).hub.online:
        raise ApiError("not_found", "Rule not found")
    return (await hub(request, p, "rule_update", {"rule_id": rule_id, "fields": body.model_dump(exclude_unset=True)}))["rule"]


@router.delete("/plants/{plant_id}/rules/{rule_id}", status_code=204)
async def delete_rule(plant_id: str, rule_id: str, request: Request, p: Principal = Depends(require("member"))):
    await hub(request, p, "rule_delete", {"rule_id": rule_id})


@router.get("/plants/{plant_id}/rules/{rule_id}/executions")
async def rule_executions(plant_id: str, rule_id: str, request: Request, p: Principal = Depends(require("viewer"))):
    return await hub(request, p, "query/rule_executions", paging(request, rule_id=rule_id))


@router.get("/alerts")
async def list_alerts(request: Request, p: Principal = Depends(require("viewer"))):
    return to_api(snap(request, "alerts_open", []))


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, request: Request, p: Principal = Depends(require("member"))):
    return (await hub(request, p, "alert_ack", {"alert_id": alert_id}))["alert"]
