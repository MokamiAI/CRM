# Daily run of recurring bills, scheduled by celery_app.conf.beat_schedule
# ("daily-recurring-costs", 06:10): each company's coming cycles become bills
# to pay (a week ahead, on that company's own calendar), then admins and
# managers hear about bills due within three days. Nothing is marked paid.
import logging

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.cost_service import CostService, RecurringCostService
from app.services.reminder_service import company_today
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)


async def _bills_and_reminders() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        set_system(session)
        company_ids = await CompanySettingsRepository(session).list_ids()
    made = reminded = 0
    for company_id in company_ids:
        # One company per transaction: a problem in one doesn't stop the rest.
        try:
            async with AsyncSessionLocal() as session:
                set_tenant(session, company_id)
                today = company_today((await CompanySettingsRepository(session).get_current()).default_timezone)
                made += await RecurringCostService(session).make_all_due(today)
                await session.commit()
                reminded += await CostService(session).remind_due(today)
                await session.commit()
        except Exception:
            logger.exception("Recurring bills failed for company %s", company_id)
    return made, reminded


@celery_app.task(name="app.tasks.cost_tasks.make_recurring_costs_task")
def make_recurring_costs_task() -> int:
    made, reminded = run_async(_bills_and_reminders)
    logger.info("Made %d recurring bill(s); sent %d bill reminder(s)", made, reminded)
    return made
