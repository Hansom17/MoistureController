"""Request handlers for watering, device actions, cancel and device configuration."""
from mc_hub.bus.requests import Ctx, RequestHandler
from mc_hub.db.models import Device, Plant
from mc_hub.errors import HubError

from . import commands, config_sync
from .domain import _need
from .views import device_view


def register(h: RequestHandler) -> None:
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
