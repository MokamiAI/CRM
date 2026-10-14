# Weekly Discovery run, scheduled by celery_app.conf.beat_schedule
# ("weekly-discovery", Monday 07:30): for each company on a plan with
# Discovery, look for new potential leads and email its admins when
# something new turned up. Nothing is added to a pipeline and no lead is
# ever contacted.
import asyncio
import logging

from sqlalchemy import select

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.plans import DISCOVERY
from app.core.tenancy import set_system, set_tenant
from app.models.discovery import DiscoveredLead
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services import platform_email
from app.services.billing_service import BillingService
from app.services.discovery_service import DiscoveryService
from app.services.reminder_service import company_today
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)

# Seconds between companies: OpenStreetMap's free servers ask for light use.
PAUSE = 5.0
REASONS = {
    "osm": "nearby business",
    "quiet_customer": "customer gone quiet",
    "lost_deal": "lost deal to revisit",
    "stale_quote": "quote with no answer",
}


def _email(to: str, company: str, leads: list[DiscoveredLead]):
    count = len(leads)
    lines = [(lead.name, REASONS.get(lead.source, "")) for lead in leads[:8]]
    more = [f"And {count - 8} more."] if count > 8 else []
    return platform_email.compose(
        to=to,
        subject=f"Discovery found {count} new lead{'s' if count != 1 else ''} for {company}",
        title=f"{count} new lead{'s' if count != 1 else ''} to look at",
        paragraphs=[
            "This week's Discovery run found potential customers for you. Nothing has been added to your pipeline "
            "and nobody has been contacted: open Discovery to add the ones worth chasing.",
            *more,
        ],
        details=lines,
        button=("Review leads", platform_email.app_link("/discovery")),
    )


async def _run_company(company_id) -> int | None:
    """New leads found, or None when the company doesn't use Discovery."""
    async with AsyncSessionLocal() as session:
        set_tenant(session, company_id)
        if DISCOVERY not in (await BillingService(session).current()).plan.features:
            return None
        service = DiscoveryService(session)
        if not (await service.settings()).enabled:
            return None
        company = await CompanySettingsRepository(session).get_current()
        found = await service.run(company_today(company.default_timezone))
        admins = list(
            (await session.scalars(select(User.email).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))).all()
        )
        if found and admins:
            await platform_email.queue(session, *(_email(a, company.company_name, found) for a in admins))
        else:
            await session.commit()
        return len(found)


async def _weekly_discovery() -> int:
    async with AsyncSessionLocal() as session:
        set_system(session)
        company_ids = await CompanySettingsRepository(session).list_ids()
    total = 0
    for company_id in company_ids:
        # One company at a time, each in its own transaction.
        try:
            found = await _run_company(company_id)
            if found is not None:
                total += found
                await asyncio.sleep(PAUSE)
        except Exception:
            logger.exception("Discovery failed for company %s", company_id)
    return total


@celery_app.task(name="app.tasks.discovery_tasks.weekly_discovery_task")
def weekly_discovery_task() -> int:
    found = run_async(_weekly_discovery)
    logger.info("Discovery found %d new lead(s)", found)
    return found
