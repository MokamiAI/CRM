import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature, require_role
from app.core.database import AsyncSessionLocal, CommitBeforeResponseRoute
from app.core.plans import DISCOVERY
from app.core.tenancy import set_tenant
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.discovery import AddLeadIn, DiscoveredLeadOut, DiscoveryRunOut, DiscoverySettingsIn, DiscoverySettingsOut
from app.services.discovery_service import DiscoveryService
from app.services.reminder_service import company_today

# Everything here is part of Scale.
router = APIRouter(prefix="/discovery", tags=["discovery"], route_class=CommitBeforeResponseRoute, dependencies=[Depends(plan_feature(DISCOVERY))])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)
_can_manage = require_role(UserRole.ADMIN, UserRole.MANAGER)
logger = logging.getLogger(__name__)
# A lookup still "looking" after this long was cut short (e.g. a restart).
LOOKING_GIVES_UP = timedelta(minutes=10)


def _settings_out(row) -> DiscoverySettingsOut:
    out = DiscoverySettingsOut.model_validate(row)
    out.located = row.latitude is not None
    if out.nearby_status == "looking" and row.nearby_checked_at and datetime.now(timezone.utc) - row.nearby_checked_at > LOOKING_GIVES_UP:
        out.nearby_status = "failed"
    return out


async def _look_nearby(company_id: uuid.UUID) -> None:
    """After "Look now" has answered: the map lookup, in its own session."""
    try:
        async with AsyncSessionLocal() as db:
            set_tenant(db, company_id)
            await DiscoveryService(db).look_nearby()
            await db.commit()
    except Exception:
        logger.exception("Discovery map lookup failed for company %s", company_id)


@router.get("/settings", response_model=DiscoverySettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return _settings_out(await DiscoveryService(db).settings())


@router.put("/settings", response_model=DiscoverySettingsOut)
async def update_settings(data: DiscoverySettingsIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_manage)):
    """Where to look and for which kinds of business. A new area is looked
    up on OpenStreetMap straight away, so a typo is caught here."""
    row = await DiscoveryService(db).update_settings(enabled=data.enabled, area=data.area, radius_km=data.radius_km, industries=list(data.industries))
    return _settings_out(row)


@router.get("/leads", response_model=list[DiscoveredLeadOut])
async def list_leads(
    status: Literal["new", "added", "dismissed"] = "new", db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    return await DiscoveryService(db).leads(status)


@router.get("/counts", response_model=dict[str, int])
async def lead_counts(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await DiscoveryService(db).counts()


@router.post("/run", response_model=DiscoveryRunOut)
async def run_now(background: BackgroundTasks, db: AsyncSession = Depends(get_db), user: User = Depends(_can_manage)):
    """Look now instead of waiting for the weekly run. Own records are
    checked straight away; nearby businesses follow in the background
    (settings.nearby_status says when). No email is sent."""
    today = company_today((await CompanySettingsRepository(db).get_current()).default_timezone)
    service = DiscoveryService(db)
    found = await service.run(today, manual=True)
    looking = DiscoveryService.can_look_nearby(await service.settings())
    if looking:
        background.add_task(_look_nearby, user.company_id)
    return DiscoveryRunOut(found=len(found), looking_nearby=looking)


@router.post("/leads/{lead_id}/add", response_model=DiscoveredLeadOut)
async def add_lead(lead_id: uuid.UUID, data: AddLeadIn | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    """Adds the lead to the pipeline as a Lead-stage deal (and a new
    customer, for a business found nearby)."""
    return await DiscoveryService(db).add_to_pipeline(lead_id, user, title=data.title if data else None)


@router.post("/leads/{lead_id}/dismiss", response_model=DiscoveredLeadOut)
async def dismiss_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    return await DiscoveryService(db).dismiss(lead_id, user)
