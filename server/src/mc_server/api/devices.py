from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from ..auth.deps import Admin, Viewer, require_recent_login
from ..db.models import Device, DeviceEvent, HealthReport
from ..errors import Problem
from ..services import commands, devices
from ..services.common import get_device
from .schemas import (
    CommandOut,
    ConfigOut,
    ConfigPut,
    DeviceActionIn,
    DeviceCreate,
    DeviceCreated,
    DeviceEventOut,
    DeviceOut,
    DevicePatch,
    HealthOut,
    PairingBundle,
)

router = APIRouter(prefix="/households/{household_id}/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(h: Viewer):
    rows = await h.uow.s.scalars(select(Device).where(
        Device.household_id == h.id, Device.deleted_at.is_(None)).order_by(Device.created_at))
    return [devices.view(d) for d in rows]


@router.post("", response_model=DeviceCreated, status_code=201)
async def create(body: DeviceCreate, h: Admin):
    device, bundle = await devices.create_device(h.uow, h.id, body.name, h.user.uid)
    return DeviceCreated(device=devices.view(device), bundle=bundle)


@router.get("/{device_id}", response_model=DeviceOut)
async def get(device_id: str, h: Viewer):
    return devices.view(await get_device(h.uow, h.id, device_id))


@router.patch("/{device_id}", response_model=DeviceOut)
async def patch(device_id: str, body: DevicePatch, h: Admin):
    device = await get_device(h.uow, h.id, device_id)
    device.name = body.name
    h.uow.emit(h.id, "device", {"id": device.id})
    await h.uow.commit()
    return devices.view(device)


@router.delete("/{device_id}", status_code=204)
async def delete(device_id: str, h: Admin, request: Request):
    await require_recent_login(request, h.user)
    await devices.delete_device(h.uow, await get_device(h.uow, h.id, device_id), h.user.uid)
    return Response(status_code=204)


@router.post("/{device_id}/rekey", response_model=PairingBundle)
async def rekey(device_id: str, h: Admin):
    return await devices.rekey(h.uow, await get_device(h.uow, h.id, device_id), h.user.uid)


@router.get("/{device_id}/config", response_model=ConfigOut)
async def get_config(device_id: str, h: Viewer):
    return devices.config_view(await get_device(h.uow, h.id, device_id))


@router.put("/{device_id}/config", response_model=ConfigOut)
async def put_config(device_id: str, body: ConfigPut, h: Admin):
    device = await get_device(h.uow, h.id, device_id)
    device = await devices.put_config(h.uow, device, body.base_rev, body.wake_interval_s,
                                      body.slots, h.user.uid)
    return devices.config_view(device)


@router.get("/{device_id}/health", response_model=list[HealthOut])
async def health(device_id: str, h: Viewer, limit: int = 500):
    await get_device(h.uow, h.id, device_id)
    rows = await h.uow.s.scalars(select(HealthReport).where(
        HealthReport.device_id == device_id).order_by(HealthReport.ts.desc())
        .limit(min(limit, 5000)))
    return list(rows)


@router.get("/{device_id}/events", response_model=list[DeviceEventOut])
async def events(device_id: str, h: Viewer, limit: int = 100):
    await get_device(h.uow, h.id, device_id)
    rows = await h.uow.s.scalars(select(DeviceEvent).where(
        DeviceEvent.device_id == device_id).order_by(DeviceEvent.ts.desc())
        .limit(min(limit, 1000)))
    return list(rows)


@router.post("/{device_id}/actions", response_model=CommandOut, status_code=202)
async def action(device_id: str, body: DeviceActionIn, h: Viewer):
    # identify: member; service mode and reboot: admin (§6.1).
    needed = "member" if body.action == "identify" else "admin"
    if not h.at_least(needed):
        raise Problem(403, "forbidden", f"requires {needed}")
    device = await get_device(h.uow, h.id, device_id)
    return commands.view(await commands.device_action(h.uow, device, body.action, body.args,
                                                      h.user.uid))
