# Daily run of recurring invoices, scheduled by celery_app.conf.beat_schedule
# ("daily-recurring-invoices", 06:00): each company's due cycles become draft
# invoices, on that company's own calendar. Nothing is sent.
import logging

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.recurring_service import RecurringInvoiceService
from app.services.reminder_service import company_today
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)


async def _make_due_drafts() -> int:
    async with AsyncSessionLocal() as session:
        set_system(session)
        company_ids = await CompanySettingsRepository(session).list_ids()
    made = 0
    for company_id in company_ids:
        # One company per transaction: a problem in one doesn't stop the rest.
        try:
            async with AsyncSessionLocal() as session:
                set_tenant(session, company_id)
                today = company_today((await CompanySettingsRepository(session).get_current()).default_timezone)
                made += await RecurringInvoiceService(session).make_all_due(today)
                await session.commit()
        except Exception:
            logger.exception("Recurring invoices failed for company %s", company_id)
    return made


@celery_app.task(name="app.tasks.recurring_tasks.make_recurring_invoices_task")
def make_recurring_invoices_task() -> int:
    made = run_async(_make_due_drafts)
    logger.info("Made %d recurring draft invoice(s)", made)
    return made
