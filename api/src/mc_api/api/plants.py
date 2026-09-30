from datetime import datetime, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import select

from ..auth.deps import Member, Viewer
from ..db.models import CommandRow
from ..db.types import utcnow
from ..services import commands, plants
from ..services.common import get_plant
from .schemas import (
    CommandOut,
    PlantCreate,
    PlantOut,
    PlantPatch,
    ReadingOut,
    RuleExecutionOut,
    RuleIn,
    RuleOut,
    RulePatch,
    WaterIn,
    WaterOut,
)

router = APIRouter(prefix="/households/{household_id}/plants", tags=["plants"])


@router.get("", response_model=list[PlantOut])
async def list_plants(h: Viewer):
    return [await plants.view(h.uow, p) for p in await plants.list_plants(h.uow, h.id)]


@router.post("", response_model=PlantOut, status_code=201)
async def create(body: PlantCreate, h: Member):
    plant = await plants.create(h.uow, h.id, body.model_dump(), h.user.uid)
    return await plants.view(h.uow, plant)


@router.get("/{plant_id}", response_model=PlantOut)
async def get(plant_id: str, h: Viewer):
    return await plants.view(h.uow, await get_plant(h.uow, h.id, plant_id))


@router.patch("/{plant_id}", response_model=PlantOut)
async def patch(plant_id: str, body: PlantPatch, h: Member):
    plant = await get_plant(h.uow, h.id, plant_id)
    plant = await plants.update(h.uow, plant, body.model_dump(exclude_unset=True))
    return await plants.view(h.uow, plant)


@router.delete("/{plant_id}", status_code=204)
async def archive(plant_id: str, h: Member):
    await plants.archive(h.uow, await get_plant(h.uow, h.id, plant_id))
    return Response(status_code=204)


@router.get("/{plant_id}/readings", response_model=list[ReadingOut])
async def readings(plant_id: str, h: Viewer, start: datetime | None = None,
                   end: datetime | None = None, bucket: str = "raw"):
    plant = await get_plant(h.uow, h.id, plant_id)
    end = end or utcnow()
    start = start or end - timedelta(days=1)
    return await plants.readings(h.uow, plant, start, end, bucket)


@router.post("/{plant_id}/water", response_model=WaterOut, status_code=202)
async def water(plant_id: str, body: WaterIn, h: Member):
    plant = await get_plant(h.uow, h.id, plant_id)
    cmd, warnings = await commands.create_pump_run(h.uow, h.id, plant, body.seconds,
                                                   source="manual", created_by=h.user.uid)
    await h.uow.commit()
    return WaterOut(command=commands.view(cmd), warnings=warnings)


@router.get("/{plant_id}/commands", response_model=list[CommandOut])
async def plant_commands(plant_id: str, h: Viewer, limit: int = 20):
    await get_plant(h.uow, h.id, plant_id)
    rows = await h.uow.s.scalars(select(CommandRow).where(
        CommandRow.household_id == h.id, CommandRow.plant_id == plant_id,
        CommandRow.action == "pump.run").order_by(CommandRow.created_at.desc())
        .limit(min(limit, 200)))
    return [commands.view(c) for c in rows]


# --- rules ------------------------------------------------------------------------------


@router.get("/{plant_id}/rules", response_model=list[RuleOut])
async def rules(plant_id: str, h: Viewer):
    plant = await get_plant(h.uow, h.id, plant_id)
    from ..db.models import Rule

    return list(await h.uow.s.scalars(select(Rule).where(Rule.plant_id == plant.id)))


@router.post("/{plant_id}/rules", response_model=RuleOut, status_code=201)
async def create_rule(plant_id: str, body: RuleIn, h: Member):
    plant = await get_plant(h.uow, h.id, plant_id)
    return await plants.create_rule(h.uow, plant, body.model_dump(), h.user.uid)


@router.patch("/{plant_id}/rules/{rule_id}", response_model=RuleOut)
async def patch_rule(plant_id: str, rule_id: str, body: RulePatch, h: Member):
    plant = await get_plant(h.uow, h.id, plant_id)
    rule = await plants.get_rule(h.uow, plant, rule_id)
    return await plants.update_rule(h.uow, rule, body.model_dump(exclude_unset=True))


@router.delete("/{plant_id}/rules/{rule_id}", status_code=204)
async def delete_rule(plant_id: str, rule_id: str, h: Member):
    plant = await get_plant(h.uow, h.id, plant_id)
    await plants.delete_rule(h.uow, await plants.get_rule(h.uow, plant, rule_id))
    return Response(status_code=204)


@router.get("/{plant_id}/rules/{rule_id}/executions", response_model=list[RuleExecutionOut])
async def executions(plant_id: str, rule_id: str, h: Viewer):
    plant = await get_plant(h.uow, h.id, plant_id)
    return await plants.executions(h.uow, await plants.get_rule(h.uow, plant, rule_id))
