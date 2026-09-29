from fastapi import APIRouter, Request, Response

from mc_core.contract.hub import (
    EnrollPollRequest,
    EnrollPollResponse,
    EnrollStartRequest,
    EnrollStartResponse,
)

from ..auth.deps import Admin, AdminSensitive, UowDep, Viewer
from ..errors import not_found
from ..services import hubs
from ..services.common import audit, get_hub
from .schemas import HubClaim, HubOut, HubPatch

router = APIRouter(tags=["hub"])
enroll_router = APIRouter(prefix="/hub/v1/enroll", tags=["hub enrollment"])


def _view(h, hub) -> HubOut:
    return HubOut(**hubs.view(hub, h.household, h.uow.ctx.settings.latest_hub_version))


@router.get("/households/{household_id}/hub", response_model=HubOut)
async def get(h: Viewer):
    hub = await get_hub(h.uow, h.id)
    if hub is None:
        raise not_found("hub")
    return _view(h, hub)


@router.post("/households/{household_id}/hub", response_model=HubOut, status_code=201)
async def claim(body: HubClaim, h: AdminSensitive):
    hub = await hubs.claim(h.uow, h.household, body.user_code, h.user.uid)
    return _view(h, hub)


@router.patch("/households/{household_id}/hub", response_model=HubOut)
async def patch(body: HubPatch, h: Admin):
    hub = await get_hub(h.uow, h.id)
    if hub is None:
        raise not_found("hub")
    hub.lan_host_override = body.lan_host_override or None
    audit(h.uow, h.id, h.user.uid, "hub.lan_host", {"lan_host_override": hub.lan_host_override})
    h.uow.emit(h.id, "hub", {})
    await h.uow.commit()
    return _view(h, hub)


@router.delete("/households/{household_id}/hub", status_code=204)
async def remove(h: AdminSensitive):
    await hubs.remove(h.uow, h.id, h.user.uid)
    return Response(status_code=204)


# --- enrollment: no user auth (hub.md §3) ----------------------------------------------


@enroll_router.post("/start", response_model=EnrollStartResponse, status_code=201)
async def start(body: EnrollStartRequest, request: Request, uow: UowDep):
    ip = request.client.host if request.client else None
    return await hubs.enroll_start(uow, body, ip)


@enroll_router.post("/poll", response_model=EnrollPollResponse,
                    responses={202: {"description": "pending"}, 410: {"description": "gone"}})
async def poll(body: EnrollPollRequest, uow: UowDep):
    result = await hubs.enroll_poll(uow, body.enroll_id, body.secret)
    if result is None:
        return Response('{"status":"pending"}', status_code=202, media_type="application/json")
    return result
