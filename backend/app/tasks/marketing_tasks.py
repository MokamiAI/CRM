# Marketing campaign delivery. send_campaign_task is queued by the API when
# a campaign is sent now, and by dispatch_scheduled_campaigns_task (beat,
# every minute) when a scheduled one falls due.
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.customer import Customer
from app.models.marketing import Campaign, CampaignRecipient
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.campaign_service import CampaignService
from app.services.email_service import EmailNotConfiguredError, send_email
from app.services.email_settings import resolve_email_config
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)

# Recipients are committed in small batches so a crash mid-run never
# re-sends to people already marked sent when the task is retried.
_BATCH = 20


@celery_app.task(name="app.tasks.marketing_tasks.send_campaign_task")
def send_campaign_task(campaign_id: str) -> int:
    async def _run() -> int:
        sent = 0
        async with AsyncSessionLocal() as session:
            set_system(session)
            service = CampaignService(session)
            campaign = await session.get(Campaign, uuid.UUID(campaign_id))
            if campaign is None or campaign.status != "sending":
                return 0
            set_tenant(session, campaign.company_id)
            config = resolve_email_config(await CompanySettingsRepository(session).get_current())
            while True:
                batch = (
                    await session.scalars(
                        select(CampaignRecipient)
                        .where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "queued")
                        .limit(_BATCH)
                    )
                ).all()
                if not batch:
                    break
                for recipient in batch:
                    try:
                        name = recipient.email.split("@")[0]
                        if recipient.customer_id:
                            customer = await session.get(Customer, recipient.customer_id)
                            name = customer.name if customer else name
                        email = await service.compose(campaign, recipient.email, name, recipient.token)
                        send_email(config, email)
                        recipient.status = "sent"
                        recipient.sent_at = datetime.now(timezone.utc)
                        sent += 1
                    except EmailNotConfiguredError:
                        recipient.status, recipient.error = "failed", "Outgoing email is not configured"
                    except Exception as exc:  # one bad address must not stop the run
                        logger.warning("Campaign %s: could not send to %s: %s", campaign_id, recipient.email, exc)
                        recipient.status, recipient.error = "failed", str(exc)[:255]
                await session.commit()
            campaign.status = "sent"
            await session.commit()
        logger.info("Campaign %s: sent %d emails", campaign_id, sent)
        return sent

    return run_async(_run)


@celery_app.task(name="app.tasks.marketing_tasks.dispatch_scheduled_campaigns_task")
def dispatch_scheduled_campaigns_task() -> int:
    async def _run() -> list[str]:
        async with AsyncSessionLocal() as session:
            set_system(session)
            due = [(c.id, c.company_id) for c in await CampaignService(session).due_campaigns()]
        started: list[str] = []
        # The audience must be resolved inside the campaign's own company.
        for campaign_id, company_id in due:
            async with AsyncSessionLocal() as session:
                set_tenant(session, company_id)
                service = CampaignService(session)
                campaign = await service.get_campaign(campaign_id)
                await service.start_sending(campaign)
                await session.commit()
                if campaign.status == "sending":
                    started.append(str(campaign.id))
        return started

    ids = run_async(_run)
    for campaign_id in ids:
        send_campaign_task.delay(campaign_id)
    return len(ids)
