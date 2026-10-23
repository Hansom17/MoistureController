"""Request handlers for watering, device actions, cancel and device configuration."""
from mc_hub.bus.requests import Ctx, RequestHandler
from mc_hub.db.models import Device, Plant
from mc_hub.errors import HubError

import json

from . import commands, config_sync, devices as devs
from .join import clean_install_code
from .domain import _need
from .views import device_view


def register(h: RequestHandler, hub) -> None:
    @h.register("water")
    async def water(ctx: Ctx, b: dict):
        _need(b, "plant_id", "seconds")
        p = await ctx.session.get(Plant, b["plant_id"])
        if p is None or p.archived_at is not None:
            raise HubError("not_found", "Plant not found")
        if p.pump_device_id is None or p.pump_slot is None:
            raise HubError("conflict", "The plant has no pump", "Assign a pump first.")
        d = await ctx.session.get(Device, p.pump_device_id)
        c = await commands.create_pump_run(ctx.session, ctx.fx, ctx.now, d, p.pump_slot, int(b["seconds"]),
                                           source="manual", created_by=ctx.actor.user_id, request_id=ctx.request_id,
                                           plant_id=p.id, ttl_s=b.get("ttl_s"))
        return {"command": commands.command_view(c)}

    @h.register("device_action")
    async def device_action(ctx: Ctx, b: dict):
        _need(b, "device_id", "action")
        d = await ctx.session.get(Device, b["device_id"])
        c = await commands.create_device_action(ctx.session, ctx.fx, ctx.now, d, b["action"],
                                                created_by=ctx.actor.user_id, request_id=ctx.request_id)
        return {"command": commands.command_view(c)}

    @h.register("command_cancel")
    async def command_cancel(ctx: Ctx, b: dict):
        _need(b, "command_id")
        c = await commands.cancel(ctx.session, ctx.fx, ctx.now, b["command_id"], created_by=ctx.actor.user_id,
                                  request_id=ctx.request_id)
        return {"command": commands.command_view(c)}

    @h.register("device_config_put")
    async def device_config_put(ctx: Ctx, b: dict):
        _need(b, "device_id", "base_rev", "config")
        d = await ctx.session.get(Device, b["device_id"])
        rev = await config_sync.put(ctx.session, ctx.fx, ctx.now, d, int(b["base_rev"]), b["config"],
                                    ctx.actor.user_id)
        ctx.emit("config", {"device_id": d.id, "rev": rev})
        ctx.emit("device", device_view(d))
        return {"rev": rev}

    @h.register("device_battery_calibrate")
    async def device_battery_calibrate(ctx: Ctx, b: dict):
        _need(b, "device_id", "measured_mv")
        d = await ctx.session.get(Device, b["device_id"])
        permille = await config_sync.calibrate(ctx.session, ctx.fx, ctx.now, d, int(b["measured_mv"]),
                                               ctx.actor.user_id)
        ctx.emit("device", device_view(d))
        return {"cal_permille": permille, "rev": d.desired_rev}

    # ---- join window and removal (Gateway/specs.md 7.3, 7.4) --------------------------------

    @h.register("device_join_open")
    async def device_join_open(ctx: Ctx, b: dict):
        seconds = int(b.get("seconds", 120))
        if not 10 <= seconds <= 254:
            raise HubError("validation", detail="seconds must be 10..254")
        if not hub.jobs.zigbee_up:
            raise HubError("conflict", "Zigbee2MQTT is not reachable")
        t = hub.topics
        if b.get("install_code"):
            try:
                code = clean_install_code(b["install_code"])
            except ValueError as e:
                raise HubError("validation", detail=str(e))
            ctx.fx.publish(t.request("install_code/add"), json.dumps({"value": code}).encode())   # verify payload
        hub.join.open(ctx.now, seconds)
        ctx.fx.publish(t.request("permit_join"), json.dumps({"time": seconds}).encode())
        ctx.touch("join")
        ctx.emit("join", dict(hub.join.state))
        return {"join": dict(hub.join.state)}

    @h.register("device_join_close")
    async def device_join_close(ctx: Ctx, b: dict):
        hub.join.close()
        ctx.fx.publish(hub.topics.request("permit_join"), json.dumps({"time": 0}).encode())
        ctx.touch("join")
        ctx.emit("join", dict(hub.join.state))
        return {}

    @h.register("device_remove")
    async def device_remove(ctx: Ctx, b: dict):
        _need(b, "device_id")
        d = await ctx.session.get(Device, b["device_id"])
        if d is None or d.deleted_at is not None:
            raise HubError("not_found", "Device not found")
        ieee = d.ieee
        await devs.soft_delete(ctx.session, ctx.fx, ctx.now, d)
        ctx.fx.publish(hub.topics.request("device/remove"),
                       json.dumps({"id": ieee, "force": bool(b.get("force", False))}).encode())
        return {}

    @h.register("backup")
    async def backup(ctx: Ctx, b: dict):
        if hub.backup is None:
            raise HubError("conflict", "No backup directory is configured")
        return await hub.backup.run(ctx.now)
