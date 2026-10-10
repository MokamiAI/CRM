# Daily payment-reminder run, scheduled by celery_app.conf.beat_schedule
# ("daily-invoice-reminder", 07:00 company time). Also triggerable on demand
# via POST /invoices/send-reminders.
import logging

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.reminder_service import ClaimedReminder, ReminderService
from app.tasks._runner import run_async
from app.tasks.email_tasks import send_invoice_reminder_task

logger = logging.getLogger(__name__)


async def _claim_due_reminders() -> list[ClaimedReminder]:
    # Each company has its own reminder schedule and time zone, so claim
    # them company by company, each in its own transaction.
    async with AsyncSessionLocal() as session:
        set_system(session)
        company_ids = await CompanySettingsRepository(session).list_ids()
    claimed: list[ClaimedReminder] = []
    for company_id in company_ids:
        async with AsyncSessionLocal() as session:
            set_tenant(session, company_id)
            claimed += await ReminderService(session).claim_due_reminders()
            await session.commit()
    return claimed


def queue_reminders(claimed: list[ClaimedReminder]) -> None:
    for reminder in claimed:
        send_invoice_reminder_task.delay(str(reminder.invoice_id))


@celery_app.task(name="app.tasks.reminder_tasks.daily_invoice_reminder_task")
def daily_invoice_reminder_task() -> int:
    """Claims every reminder that's due (committed first, so a crash here
    can't lead to a duplicate later) and queues one email per invoice."""
    claimed = run_async(_claim_due_reminders)
    queue_reminders(claimed)
    logger.info("Queued %d invoice reminder(s)", len(claimed))
    return len(claimed)
