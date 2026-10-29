import uuid

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import MARKETING
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.marketing import (
    AudiencePreview,
    AudienceQuery,
    CampaignIn,
    CampaignOut,
    CampaignSchedule,
    CampaignStats,
    ConsentIn,
    InviteIn,
    PreviewOut,
    RecipientOut,
    SegmentIn,
    SegmentOut,
)
from app.services.campaign_service import CampaignService
from app.schemas.customer import CustomerOut
from app.services.prospect_service import ProspectService
from app.services.email_service import send_email
from app.services.email_settings import resolve_email_config
from app.services.segment_service import SegmentService
from app.tasks.marketing_tasks import send_campaign_task

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/marketing", tags=["marketing"])

# Anyone but a viewer can draft; sending to customers is a manager decision.
_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)
_can_send = require_role(UserRole.ADMIN, UserRole.MANAGER)
_marketing = [Depends(plan_feature(MARKETING))]


async def _out(service: CampaignService, campaign) -> CampaignOut:
    stats = (await service.stats_for([campaign.id])).get(campaign.id, CampaignStats())
    return CampaignOut.model_validate(campaign).model_copy(update={"stats": stats})


# ---------- Audiences ----------


@router.get("/segments", response_model=list[SegmentOut])
async def list_segments(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await SegmentService(db).list_segments()


@router.post("/segments", response_model=SegmentOut, status_code=201, dependencies=_marketing)
async def create_segment(data: SegmentIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await SegmentService(db).create_segment(data)


@router.put("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(
    segment_id: uuid.UUID, data: SegmentIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    return await SegmentService(db).update_segment(segment_id, data)


@router.delete("/segments/{segment_id}", status_code=204)
async def delete_segment(segment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await SegmentService(db).delete_segment(segment_id)


@router.post("/audience/preview", response_model=AudiencePreview)
async def preview_audience(data: AudienceQuery, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Who matches these rules right now (works for unsaved rules too)."""
    count, sample = await SegmentService(db).preview([r.model_dump() for r in data.rules])
    return AudiencePreview(count=count, sample=sample)


# ---------- Campaigns ----------


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = CampaignService(db)
    campaigns = await service.list_campaigns()
    stats = await service.stats_for([c.id for c in campaigns])
    return [
        CampaignOut.model_validate(c).model_copy(update={"stats": stats.get(c.id, CampaignStats())})
        for c in campaigns
    ]


@router.post("/campaigns", response_model=CampaignOut, status_code=201, dependencies=_marketing)
async def create_campaign(data: CampaignIn, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    service = CampaignService(db)
    return await _out(service, await service.create_campaign(data, created_by=user.id))


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = CampaignService(db)
    return await _out(service, await service.get_campaign(campaign_id))


@router.put("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID, data: CampaignIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    service = CampaignService(db)
    return await _out(service, await service.update_campaign(campaign_id, data))


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await CampaignService(db).delete_campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/duplicate", response_model=CampaignOut, status_code=201, dependencies=_marketing)
async def duplicate_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    service = CampaignService(db)
    return await _out(service, await service.duplicate(campaign_id, created_by=user.id))


@router.get("/campaigns/{campaign_id}/preview", response_model=PreviewOut)
async def preview_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = CampaignService(db)
    campaign = await service.get_campaign(campaign_id)
    email = await service.compose(campaign, user.email, "Thandi", token=None)
    return PreviewOut(subject=email.subject, html=email.html)


@router.post("/campaigns/{campaign_id}/test", response_model=dict, dependencies=_marketing)
async def send_test(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    """Sends this campaign to the signed-in user, untracked."""
    service = CampaignService(db)
    campaign = await service.get_campaign(campaign_id)
    email = await service.compose(campaign, user.email, user.full_name.split(" ")[0], token=None)
    config = resolve_email_config(await CompanySettingsRepository(db).get_current())
    await run_in_threadpool(send_email, config, email)
    return {"sent_to": user.email}


@router.post("/campaigns/{campaign_id}/send", response_model=CampaignOut, dependencies=_marketing)
async def send_campaign(
    campaign_id: uuid.UUID,
    data: CampaignSchedule,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_send),
):
    service = CampaignService(db)
    campaign = await service.schedule(campaign_id, data.scheduled_at)
    if campaign.status == "sending":
        await commit_and_enqueue(db, send_campaign_task, str(campaign.id))
    return await _out(service, campaign)


@router.post("/campaigns/{campaign_id}/unschedule", response_model=CampaignOut)
async def unschedule_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_send)):
    service = CampaignService(db)
    return await _out(service, await service.unschedule(campaign_id))


@router.get("/campaigns/{campaign_id}/recipients", response_model=list[RecipientOut])
async def campaign_recipients(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await CampaignService(db).recipients(campaign_id)
    return [RecipientOut.model_validate(r).model_copy(update={"customer_name": name}) for r, name in rows]


# ---------- Prospects and consent (POPIA s69) ----------


@router.get("/prospects", response_model=list[CustomerOut], dependencies=_marketing)
async def list_prospects(search: str | None = None, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await ProspectService(db).list_prospects(search)


@router.put("/prospects/{prospect_id}/consent", response_model=CustomerOut, dependencies=_marketing)
async def set_consent(prospect_id: uuid.UUID, data: ConsentIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await ProspectService(db).set_consent(prospect_id, data.agreed, data.source)


@router.post("/prospects/{prospect_id}/invite", response_model=CustomerOut, dependencies=_marketing)
async def invite_prospect(prospect_id: uuid.UUID, data: InviteIn, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    """The one-time email asking whether they'd like to hear from you."""
    return await ProspectService(db).invite(prospect_id, data.subject, data.message)
