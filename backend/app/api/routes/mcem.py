import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.mcem import EvidenceCreate, ExpansionCreate, JourneyUpdate, MilestoneUpdate
from app.services.mcem_service import McemService

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["mcem"])
write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.get("/mcem/report")
async def report(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return jsonable_encoder(await McemService(db).report())


@router.get("/deals/{deal_id}/mcem")
async def detail(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return jsonable_encoder(await McemService(db).detail(deal_id))


@router.post("/deals/{deal_id}/mcem/enable")
async def enable(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(write)):
    return jsonable_encoder(await McemService(db).enable(deal_id, user))


@router.patch("/deals/{deal_id}/mcem/journey")
async def journey(deal_id: uuid.UUID, data: JourneyUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(write)):
    return jsonable_encoder(await McemService(db).update_journey(deal_id, data, user))


@router.patch("/deals/{deal_id}/mcem/milestones/{key}")
async def milestone(deal_id: uuid.UUID, key: str, data: MilestoneUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(write)):
    return jsonable_encoder(await McemService(db).update_milestone(deal_id, key, data, user))


@router.get("/deals/{deal_id}/mcem/sources")
async def sources(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return jsonable_encoder(await McemService(db).sources(deal_id))


@router.get("/deals/{deal_id}/mcem/history")
async def history(deal_id: uuid.UUID, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return jsonable_encoder(await McemService(db).history(deal_id, offset, limit))


@router.post("/deals/{deal_id}/mcem/milestones/{key}/evidence", status_code=201)
async def evidence(deal_id: uuid.UUID, key: str, data: EvidenceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(write)):
    return jsonable_encoder(await McemService(db).add_evidence(deal_id, key, data, user))


@router.post("/deals/{deal_id}/mcem/expansions", status_code=201)
async def expansion(deal_id: uuid.UUID, data: ExpansionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(write)):
    return jsonable_encoder(await McemService(db).expansion(deal_id, data, user))
