"""Recurring invoices: retainers and contracts billed on a schedule.

Each cycle makes a DRAFT invoice through the normal invoice path (same
numbering, VAT and totals as one made by hand) and never sends it. A cycle is
made once: the schedule row is locked while it runs, an existing invoice for
that cycle is skipped, and invoices(recurring_invoice_id, recurrence_date) is
unique in the database as a backstop.
"""
# Lazy annotations: the service's own list() method would otherwise shadow
# list[...] in its signatures on Python 3.12.
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.plans import RECURRING
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.recurring import RecurringInvoice
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.schemas.recurring import RecurringInvoiceCreate, RecurringInvoiceUpdate
from app.services.pricing import build_line_items

logger = logging.getLogger(__name__)

MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
# A schedule that fell far behind (switched off, or the server down) makes at
# most this many catch-up drafts in one run, so nobody wakes up to a pile.
MAX_CATCH_UP = 12


def add_months(start: date, months: int) -> date:
    """start + months, keeping start's day where the month has it (the 31st
    becomes 30 April and 28 or 29 February)."""
    month0 = start.month - 1 + months
    year, month = start.year + month0 // 12, month0 % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def next_cycle(schedule: RecurringInvoice, current: date) -> date:
    """The cycle after `current`, counted from the start date so month-end
    days don't drift (31 Jan, 28 Feb, 31 Mar, not 31 Jan, 28 Feb, 28 Mar)."""
    if schedule.frequency == "weekly":
        return current + timedelta(days=7)
    step = MONTHS[schedule.frequency]
    elapsed = (current.year - schedule.start_date.year) * 12 + current.month - schedule.start_date.month
    return add_months(schedule.start_date, (elapsed // step + 1) * step)


def _items(schedule: RecurringInvoice) -> list[InvoiceItemCreate]:
    return [InvoiceItemCreate(**item) for item in schedule.items]


def schedule_total(schedule: RecurringInvoice) -> Decimal:
    _, _, _, total = build_line_items(InvoiceItem, _items(schedule))
    return total


def _stored_items(items: list[InvoiceItemCreate]) -> list[dict]:
    return [
        {
            "product_id": str(i.product_id) if i.product_id else None,
            "description": i.description,
            "quantity": str(i.quantity),
            "unit_price": str(i.unit_price),
            "tax_rate": str(i.tax_rate),
        }
        for i in items
    ]


class RecurringInvoiceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, schedule_id: uuid.UUID, lock: bool = False) -> RecurringInvoice:
        stmt = select(RecurringInvoice).where(RecurringInvoice.id == schedule_id)
        if lock:
            stmt = stmt.with_for_update()
        schedule = await self.db.scalar(stmt)
        if schedule is None:
            raise NotFoundError("Recurring invoice not found", "RECURRING_NOT_FOUND")
        return schedule

    async def list(self) -> list[RecurringInvoice]:
        rows = await self.db.scalars(select(RecurringInvoice).order_by(RecurringInvoice.active.desc(), RecurringInvoice.next_run_date))
        return list(rows.all())

    async def invoices_made(self, schedule_id: uuid.UUID) -> list[Invoice]:
        rows = await self.db.scalars(
            select(Invoice).where(Invoice.recurring_invoice_id == schedule_id).order_by(Invoice.recurrence_date.desc()).limit(24)
        )
        return list(rows.all())

    async def create(self, data: RecurringInvoiceCreate, created_by: uuid.UUID, today: date) -> RecurringInvoice:
        customer = await self.db.scalar(select(Customer).where(Customer.id == data.customer_id))
        if customer is None or not customer.is_active:
            raise NotFoundError("Customer not found or inactive", "CUSTOMER_NOT_FOUND")
        schedule = RecurringInvoice(
            customer_id=data.customer_id,
            frequency=data.frequency,
            start_date=data.start_date,
            next_run_date=data.start_date,
            end_date=data.end_date,
            due_days=data.due_days,
            reference=(data.reference or "").strip() or None,
            po_number=(data.po_number or "").strip() or None,
            notes=data.notes,
            items=_stored_items(data.items),
            created_by=created_by,
        )
        self.db.add(schedule)
        await self.db.flush()
        # Starting today or earlier: the first draft is ready straight away.
        await self.make_due(schedule, today)
        return schedule

    async def update(self, schedule_id: uuid.UUID, data: RecurringInvoiceUpdate) -> RecurringInvoice:
        schedule = await self.get(schedule_id, lock=True)
        changes = data.model_dump(exclude_unset=True)
        if "items" in changes:
            schedule.items = _stored_items(data.items)
            changes.pop("items")
        for field in ("reference", "po_number"):
            if field in changes:
                changes[field] = (changes[field] or "").strip() or None
        for field, value in changes.items():
            setattr(schedule, field, value)
        await self.db.flush()
        return schedule

    async def set_active(self, schedule_id: uuid.UUID, active: bool, today: date) -> RecurringInvoice:
        schedule = await self.get(schedule_id, lock=True)
        schedule.active = active
        if active and schedule.next_run_date < today:
            # Resuming skips the cycles missed while paused.
            while schedule.next_run_date < today:
                schedule.next_run_date = next_cycle(schedule, schedule.next_run_date)
        await self.db.flush()
        return schedule

    async def delete(self, schedule_id: uuid.UUID) -> None:
        schedule = await self.get(schedule_id, lock=True)
        await self.db.delete(schedule)  # its invoices stay, unlinked
        await self.db.flush()

    async def make_due(self, schedule: RecurringInvoice, today: date) -> list[Invoice]:
        """Makes the drafts for every cycle due on or before today."""
        # Imported here: the billing and invoice services import widely.
        from app.services.billing_service import BillingService, PlanLimitError
        from app.services.invoice_service import InvoiceService

        made: list[Invoice] = []
        schedule = await self.get(schedule.id, lock=True)
        while schedule.active and schedule.next_run_date <= today and len(made) < MAX_CATCH_UP:
            cycle = schedule.next_run_date
            if schedule.end_date and cycle > schedule.end_date:
                schedule.active = False
                break
            exists = await self.db.scalar(
                select(Invoice.id).where(Invoice.recurring_invoice_id == schedule.id, Invoice.recurrence_date == cycle)
            )
            if not exists:
                try:
                    await BillingService(self.db).check_room("invoices_this_month")
                except PlanLimitError:
                    logger.info("Recurring invoice %s waits: plan has no room this month", schedule.id)
                    break
                invoice = await InvoiceService(self.db).create_invoice(
                    InvoiceCreate(
                        customer_id=schedule.customer_id,
                        issue_date=cycle,
                        due_date=cycle + timedelta(days=schedule.due_days) if schedule.due_days is not None else None,
                        notes=schedule.notes,
                        po_number=schedule.po_number,
                        reference=schedule.reference,
                        items=_items(schedule),
                    ),
                    created_by_id=schedule.created_by,
                )
                invoice.recurring_invoice_id, invoice.recurrence_date = schedule.id, cycle
                made.append(invoice)
            schedule.next_run_date = next_cycle(schedule, cycle)
            if schedule.end_date and schedule.next_run_date > schedule.end_date:
                schedule.active = False
        await self.db.flush()
        return made

    async def make_all_due(self, today: date) -> int:
        """The daily run. On a plan without recurring invoices the schedules
        wait; after an upgrade the missed cycles are made as drafts."""
        from app.services.billing_service import BillingService

        if RECURRING not in (await BillingService(self.db).current()).plan.features:
            return 0
        ids = await self.db.scalars(
            select(RecurringInvoice.id).where(RecurringInvoice.active.is_(True), RecurringInvoice.next_run_date <= today)
        )
        count = 0
        for schedule_id in ids.all():
            count += len(await self.make_due(await self.get(schedule_id), today))
        return count
