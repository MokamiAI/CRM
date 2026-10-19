import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.tenancy import current_company_id
from app.models.customer import Customer
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.reminder import ReminderLog
from app.repositories.company_settings_repository import CompanySettingsRepository

# Invoices a customer still owes money on.
REMINDABLE = {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE}


def schedule_key(offset: int) -> str:
    return f"schedule:{offset}"


def pick_reminder_step(offsets: list[int], days_past_due: int) -> int | None:
    """The schedule step an invoice is currently at: the latest offset that
    has been reached, or None if the first one hasn't come round yet.

    Only the latest step is ever sent. If the scheduler was down for a few
    days, or reminders were just switched on, the customer gets one
    reminder for where the invoice is now, never a burst of missed ones."""
    reached = [offset for offset in offsets if offset <= days_past_due]
    return max(reached) if reached else None


def company_today(tz_name: str) -> date:
    """'Today' in the company's timezone, not the server's: a 07:00 run in
    Johannesburg is still the previous day in UTC."""
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class ClaimedReminder:
    log_id: uuid.UUID
    invoice_id: uuid.UUID
    reminder_type: str


class ReminderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)

    async def _claim(self, invoice_id: uuid.UUID, reminder_type: str) -> uuid.UUID | None:
        """Records a reminder as sent before it goes out. The unique
        (invoice_id, reminder_type) constraint makes this the dedup point:
        two overlapping runs can't both claim the same step, so a customer
        is never reminded twice for it. If delivery then fails for good,
        the step stays claimed: a missed reminder is better than a
        duplicate one."""
        result = await self.db.execute(
            insert(ReminderLog)
            .values(
                id=uuid.uuid4(),
                company_id=current_company_id(self.db),
                invoice_id=invoice_id,
                reminder_type=reminder_type,
                sent_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(constraint="uq_reminder_invoice_type")
            .returning(ReminderLog.id)
        )
        return result.scalar_one_or_none()

    async def claim_due_reminders(self) -> list[ClaimedReminder]:
        """Finds every open invoice whose schedule step has been reached and
        not yet reminded, and claims it. Callers commit, then queue the
        emails (app/tasks/reminder_tasks.py)."""
        settings_row = await self.company_settings.get_current()
        if not settings_row.reminders_enabled or not settings_row.reminder_offsets:
            return []
        today = company_today(settings_row.default_timezone)

        rows = await self.db.execute(
            select(Invoice.id, Invoice.due_date)
            .join(Customer, Customer.id == Invoice.customer_id)
            .where(Invoice.status.in_(REMINDABLE), Customer.recipient_email.is_not(None), Customer.recipient_email != "")
        )
        claimed: list[ClaimedReminder] = []
        for invoice_id, due_date in rows.all():
            step = pick_reminder_step(settings_row.reminder_offsets, (today - due_date).days)
            if step is None:
                continue
            key = schedule_key(step)
            log_id = await self._claim(invoice_id, key)
            if log_id is not None:
                claimed.append(ClaimedReminder(log_id, invoice_id, key))
        return claimed

    async def claim_manual_reminder(self, invoice_id: uuid.UUID) -> ClaimedReminder:
        invoice = await self.db.get(Invoice, invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        if invoice.status not in REMINDABLE:
            raise ConflictError(
                f"Only unpaid sent invoices can be reminded (this one is {invoice.status.value})",
                "INVOICE_NOT_REMINDABLE",
            )
        customer = await self.db.get(Customer, invoice.customer_id)
        if customer is None or not customer.recipient_email:
            raise ConflictError("Contact person's email not found. Add an email to their contact details.", "CUSTOMER_NO_EMAIL")
        # Manual reminders are never deduplicated against each other or the
        # schedule: the timestamp makes each one its own reminder_type.
        key = f"manual:{datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        log_id = await self._claim(invoice_id, key)
        if log_id is None:
            raise ConflictError("A reminder was just sent for this invoice", "REMINDER_JUST_SENT")
        return ClaimedReminder(log_id, invoice_id, key)

    async def history(self, invoice_id: uuid.UUID) -> list[ReminderLog]:
        result = await self.db.execute(
            select(ReminderLog).where(ReminderLog.invoice_id == invoice_id).order_by(ReminderLog.sent_at.desc())
        )
        return list(result.scalars().all())
