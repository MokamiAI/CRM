"""Costs: what a company spends, one-off or recurring, and what's left.

Money counts when it moves: money in is payments received, money out is
costs paid, in the company's own time zone. A recurring bill makes each
cycle's bill a week before it's due and leaves it to be marked paid: a bill
that marked itself paid would quietly make the figures wrong.
"""
# Lazy annotations: the services' own list() methods would otherwise shadow
# list[...] in their signatures on Python 3.12.
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.cost import Cost, RecurringCost
from app.models.enums import PurchaseOrderStatus, UserRole
from app.models.payment import Payment
from app.models.purchasing import PurchaseOrder, Supplier
from app.models.user import User
from app.schemas.cost import CostCreate, CostFromPurchaseOrder, CostUpdate, RecurringCostCreate, RecurringCostUpdate
from app.services.attachment_service import MAX_BYTES, TYPES, _clean_name
from app.services.recurring_service import MAX_CATCH_UP, next_cycle

logger = logging.getLogger(__name__)

# A recurring bill appears this many days before it's due.
LEAD_DAYS = 7
# People are reminded of a bill this many days before it's due.
REMIND_DAYS = 3
RECEIPT_TYPES = {ext: kind for ext, kind in TYPES.items() if ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic")}
ZERO = Decimal("0.00")


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-11' -> (1 Nov, 1 Dec)."""
    try:
        year, mon = (int(part) for part in month.split("-"))
        start = date(year, mon, 1)
    except ValueError as exc:
        raise AppError("Give the month as YYYY-MM", "COST_BAD_MONTH", 422) from exc
    return start, date(year + mon // 12, mon % 12 + 1, 1)


class CostService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, cost_id: uuid.UUID, lock: bool = False, with_receipt: bool = False) -> Cost:
        stmt = select(Cost).where(Cost.id == cost_id)
        if lock:
            stmt = stmt.with_for_update()
        if with_receipt:
            stmt = stmt.options(undefer(Cost.receipt_data))
        cost = await self.db.scalar(stmt)
        if cost is None:
            raise NotFoundError("Cost not found", "COST_NOT_FOUND")
        return cost

    async def _check_supplier(self, supplier_id: uuid.UUID | None) -> None:
        if supplier_id and await self.db.scalar(select(Supplier.id).where(Supplier.id == supplier_id)) is None:
            raise NotFoundError("Supplier not found", "SUPPLIER_NOT_FOUND")

    def _filtered(self, stmt, status: str | None, category: str | None, start: date | None, end: date | None):
        """Paid costs filter by the day they were paid, bills by their due date."""
        if status:
            stmt = stmt.where(Cost.status == status)
        if category:
            stmt = stmt.where(Cost.category == category)
        day = func.coalesce(Cost.paid_date, Cost.due_date)
        if start:
            stmt = stmt.where(day >= start)
        if end:
            stmt = stmt.where(day <= end)
        return stmt

    async def list(
        self, status: str | None = None, category: str | None = None, start: date | None = None, end: date | None = None, limit: int = 500
    ) -> tuple[list[Cost], Decimal, Decimal]:
        stmt = self._filtered(select(Cost), status, category, start, end)
        rows = await self.db.scalars(stmt.order_by(func.coalesce(Cost.paid_date, Cost.due_date).desc(), Cost.created_at.desc()).limit(limit))
        sums = dict(
            (await self.db.execute(self._filtered(select(Cost.status, func.sum(Cost.amount)), status, category, start, end).group_by(Cost.status))).all()
        )
        return list(rows.all()), sums.get("paid") or ZERO, sums.get("due") or ZERO

    async def categories(self) -> list[str]:
        """Every category the company has used, the ready-made ones first in the app."""
        rows = await self.db.scalars(select(Cost.category).distinct())
        recurring = await self.db.scalars(select(RecurringCost.category).distinct())
        return sorted(set(rows.all()) | set(recurring.all()))

    async def create(self, data: CostCreate, user: User, today: date) -> Cost:
        await self._check_supplier(data.supplier_id)
        cost = Cost(
            description=data.description.strip(),
            category=data.category,
            amount=data.amount,
            due_date=data.due_date,
            status="paid" if data.paid else "due",
            paid_date=(data.paid_date or min(data.due_date, today)) if data.paid else None,
            supplier_id=data.supplier_id,
            notes=data.notes,
            created_by=user.id,
        )
        self.db.add(cost)
        await self.db.flush()
        return cost

    async def update(self, cost_id: uuid.UUID, data: CostUpdate) -> Cost:
        cost = await self.get(cost_id, lock=True)
        changes = data.model_dump(exclude_unset=True)
        if "supplier_id" in changes:
            await self._check_supplier(changes["supplier_id"])
        for field in ("description", "category", "amount", "due_date", "paid_date"):
            if field in changes and changes[field] is None:
                changes.pop(field)
        if cost.status != "paid":
            changes.pop("paid_date", None)  # a bill gets its paid date when it's paid
        for field, value in changes.items():
            setattr(cost, field, value.strip() if field == "description" else value)
        await self.db.flush()
        return cost

    async def set_paid(self, cost_id: uuid.UUID, paid: bool, paid_date: date | None, today: date) -> Cost:
        cost = await self.get(cost_id, lock=True)
        cost.status = "paid" if paid else "due"
        cost.paid_date = (paid_date or today) if paid else None
        await self.db.flush()
        return cost

    async def delete(self, cost_id: uuid.UUID) -> None:
        cost = await self.get(cost_id, lock=True)
        await self.db.delete(cost)
        await self.db.flush()

    async def add_receipt(self, cost_id: uuid.UUID, filename: str | None, content: bytes) -> Cost:
        cost = await self.get(cost_id, lock=True)
        name = _clean_name(filename)
        kind = RECEIPT_TYPES.get(os.path.splitext(name)[1].lower())
        if kind is None or (kind[1] and not content.startswith(kind[1])):
            raise AppError("Add a photo (JPG, PNG, WEBP, HEIC) or a PDF of the receipt", "RECEIPT_BAD_TYPE", 422)
        if not content:
            raise AppError("That file is empty", "ATTACHMENT_EMPTY", 422)
        if len(content) > MAX_BYTES:
            raise AppError("Each file must be 10 MB or smaller", "ATTACHMENT_TOO_LARGE", 413)
        cost.receipt_name, cost.receipt_type, cost.receipt_size, cost.receipt_data = name, kind[0], len(content), content
        await self.db.flush()
        return cost

    async def remove_receipt(self, cost_id: uuid.UUID) -> Cost:
        cost = await self.get(cost_id, lock=True)
        cost.receipt_name = cost.receipt_type = cost.receipt_size = cost.receipt_data = None
        await self.db.flush()
        return cost

    async def from_purchase_order(self, po_id: uuid.UUID, data: CostFromPurchaseOrder, user: User, today: date) -> Cost:
        """A purchase order that was sent or received, recorded once as a cost."""
        po = await self.db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update())
        if po is None:
            raise NotFoundError("Purchase order not found", "PURCHASE_ORDER_NOT_FOUND")
        if po.status not in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.RECEIVED):
            raise ConflictError("Send or receive the purchase order before recording it as a cost", "COST_PO_NOT_SENT")
        if await self.db.scalar(select(Cost.id).where(Cost.purchase_order_id == po_id)) is not None:
            raise ConflictError("This purchase order is already recorded as a cost", "COST_PO_ALREADY")
        if not po.total or Decimal(po.total) <= 0:
            raise ConflictError("This purchase order has no amount to record", "COST_PO_EMPTY")
        supplier = await self.db.get(Supplier, po.supplier_id)
        due = po.delivery_date or po.issue_date
        cost = Cost(
            description=f"{po.po_number} · {supplier.name}" if supplier else po.po_number,
            category=data.category,
            amount=po.total,
            due_date=due,
            status="paid" if data.paid else "due",
            paid_date=(data.paid_date or today) if data.paid else None,
            supplier_id=po.supplier_id,
            purchase_order_id=po.id,
            created_by=user.id,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(cost)
                await self.db.flush()
        except IntegrityError as exc:  # recorded by another request a moment ago
            raise ConflictError("This purchase order is already recorded as a cost", "COST_PO_ALREADY") from exc
        return cost

    async def for_purchase_order(self, po_id: uuid.UUID) -> Cost | None:
        return await self.db.scalar(select(Cost).where(Cost.purchase_order_id == po_id))

    async def summary(self, month: str, today: date, tz: str) -> dict:
        start, end = month_bounds(month)
        zone = ZoneInfo(tz or "Africa/Johannesburg")
        money_in = await self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.paid_at >= datetime.combine(start, time.min, zone), Payment.paid_at < datetime.combine(end, time.min, zone)
            )
        )
        money_out = await self.db.scalar(
            select(func.coalesce(func.sum(Cost.amount), 0)).where(Cost.status == "paid", Cost.paid_date >= start, Cost.paid_date < end)
        )
        money_in, money_out = Decimal(money_in).quantize(ZERO), Decimal(money_out).quantize(ZERO)
        profit = money_in - money_out
        to_pay = await self.db.scalar(select(func.coalesce(func.sum(Cost.amount), 0)).where(Cost.status == "due"))
        overdue = await self.db.scalar(select(func.count()).select_from(Cost).where(Cost.status == "due", Cost.due_date < today))
        upcoming = await self.db.scalars(
            select(Cost).where(Cost.status == "due", Cost.due_date <= today + timedelta(days=30)).order_by(Cost.due_date).limit(20)
        )
        return {
            "month": month,
            "money_in": money_in,
            "money_out": money_out,
            "profit": profit,
            "margin": (profit * 100 / money_in).quantize(Decimal("0.1")) if money_in > 0 else None,
            "to_pay": Decimal(to_pay).quantize(ZERO),
            "overdue": overdue,
            "upcoming": list(upcoming.all()),
        }

    async def overview(self, today: date, tz: str, months: int = 12) -> dict:
        """The Money dashboard: money in, money out and profit for each of the
        last `months` months (oldest first, empty months included), where
        the money went by category, and what's still to come in and to pay."""
        from app.models.enums import InvoiceStatus
        from app.models.invoice import Invoice
        from app.services.report_service import OPEN_INVOICE, _month_start

        first = _month_start(today, months - 1)
        zone = ZoneInfo(tz or "Africa/Johannesburg")
        # Payments by the month they landed in, on the company's own clock.
        local_paid = func.date_trunc("month", func.timezone(tz or "Africa/Johannesburg", Payment.paid_at))
        rows = await self.db.execute(
            select(local_paid, func.sum(Payment.amount)).where(Payment.paid_at >= datetime.combine(first, time.min, zone)).group_by(local_paid)
        )
        money_in = {m.date(): Decimal(total) for m, total in rows.all()}
        paid_month = cast(func.date_trunc("month", Cost.paid_date), Date)
        rows = await self.db.execute(
            select(paid_month, func.sum(Cost.amount)).where(Cost.status == "paid", Cost.paid_date >= first).group_by(paid_month)
        )
        money_out = {m: Decimal(total) for m, total in rows.all()}
        series = []
        for back in range(months - 1, -1, -1):
            month = _month_start(today, back)
            got, spent = money_in.get(month, ZERO), money_out.get(month, ZERO)
            series.append({"month": month.isoformat(), "money_in": got, "money_out": spent, "profit": got - spent})

        async def by_category(since: date) -> list[dict]:
            rows = await self.db.execute(
                select(Cost.category, func.sum(Cost.amount), func.count())
                .where(Cost.status == "paid", Cost.paid_date >= since)
                .group_by(Cost.category)
                .order_by(func.sum(Cost.amount).desc())
            )
            return [{"category": c, "total": Decimal(total), "count": n} for c, total, n in rows.all()]

        total_in = sum((m["money_in"] for m in series), ZERO)
        total_out = sum((m["money_out"] for m in series), ZERO)
        balance = Invoice.total - Invoice.amount_paid
        to_come_in = await self.db.scalar(select(func.coalesce(func.sum(balance), 0)).where(Invoice.status.in_(OPEN_INVOICE)))
        overdue_in = await self.db.scalar(
            select(func.coalesce(func.sum(balance), 0)).where(Invoice.status == InvoiceStatus.OVERDUE)
        )
        to_pay = await self.db.scalar(select(func.coalesce(func.sum(Cost.amount), 0)).where(Cost.status == "due"))
        overdue_out = await self.db.scalar(
            select(func.coalesce(func.sum(Cost.amount), 0)).where(Cost.status == "due", Cost.due_date < today)
        )
        return {
            "months": series,
            "money_in": total_in,
            "money_out": total_out,
            "profit": total_in - total_out,
            "margin": ((total_in - total_out) * 100 / total_in).quantize(Decimal("0.1")) if total_in > 0 else None,
            "by_category": await by_category(first),
            "by_category_this_month": await by_category(_month_start(today)),
            "to_come_in": Decimal(to_come_in).quantize(ZERO),
            "overdue_in": Decimal(overdue_in).quantize(ZERO),
            "to_pay": Decimal(to_pay).quantize(ZERO),
            "overdue_out": Decimal(overdue_out).quantize(ZERO),
        }

    async def remind_due(self, today: date) -> int:
        """Tells admins and managers, once per bill, when it's due within
        REMIND_DAYS (or already overdue)."""
        from app.services import notify

        bills = (await self.db.scalars(
            select(Cost).where(Cost.status == "due", Cost.due_date <= today + timedelta(days=REMIND_DAYS)).order_by(Cost.due_date)
        )).all()
        if not bills:
            return 0
        people = (await self.db.scalars(
            select(User).where(User.is_active.is_(True), User.role.in_([UserRole.ADMIN, UserRole.MANAGER]))
        )).all()
        sent = 0
        for bill in bills:
            amount = f"R {Decimal(bill.amount):,.2f}".replace(",", " ")
            if bill.due_date < today:
                title = f"Overdue bill: {bill.description} ({amount}, due {bill.due_date:%d %b})"
            else:
                title = f"Bill due {'today' if bill.due_date == today else f'on {bill.due_date:%d %b}'}: {bill.description} ({amount})"
            for person in people:
                note = await notify.notify(
                    self.db,
                    person,
                    kind="bill_due",
                    title=title,
                    body="Mark it paid in YGT once it's paid, so your figures stay right.",
                    link="/costs",
                    params={"description": bill.description, "amount": str(bill.amount), "due": bill.due_date.isoformat(), "overdue": bill.due_date < today},
                    key=f"bill_due:{bill.id}:{bill.due_date.isoformat()}",
                )
                sent += note is not None
        return sent


class RecurringCostService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, schedule_id: uuid.UUID, lock: bool = False) -> RecurringCost:
        stmt = select(RecurringCost).where(RecurringCost.id == schedule_id)
        if lock:
            stmt = stmt.with_for_update()
        schedule = await self.db.scalar(stmt)
        if schedule is None:
            raise NotFoundError("Recurring bill not found", "RECURRING_COST_NOT_FOUND")
        return schedule

    async def list(self) -> list[RecurringCost]:
        rows = await self.db.scalars(select(RecurringCost).order_by(RecurringCost.active.desc(), RecurringCost.next_run_date))
        return list(rows.all())

    async def create(self, data: RecurringCostCreate, user: User, today: date) -> RecurringCost:
        await CostService(self.db)._check_supplier(data.supplier_id)
        schedule = RecurringCost(
            description=data.description.strip(),
            category=data.category,
            amount=data.amount,
            frequency=data.frequency,
            start_date=data.start_date,
            next_run_date=data.start_date,
            end_date=data.end_date,
            supplier_id=data.supplier_id,
            notes=data.notes,
            created_by=user.id,
        )
        # Started in the past: only the latest cycle is billed (this month's
        # rent, say), not every month since the lease began.
        while next_cycle(schedule, schedule.next_run_date) <= today:
            schedule.next_run_date = next_cycle(schedule, schedule.next_run_date)
        self.db.add(schedule)
        await self.db.flush()
        await self.make_due(schedule, today)
        return schedule

    async def update(self, schedule_id: uuid.UUID, data: RecurringCostUpdate, today: date) -> RecurringCost:
        schedule = await self.get(schedule_id, lock=True)
        changes = data.model_dump(exclude_unset=True)
        if "supplier_id" in changes:
            await CostService(self.db)._check_supplier(changes["supplier_id"])
        for field in ("description", "category", "amount", "frequency", "next_run_date"):
            if field in changes and changes[field] is None:
                changes.pop(field)
        if changes.get("next_run_date") and changes["next_run_date"] != schedule.next_run_date:
            # A new next date re-anchors the schedule (the 20th stays the 20th).
            schedule.start_date = changes["next_run_date"]
        for field, value in changes.items():
            setattr(schedule, field, value.strip() if field == "description" else value)
        while next_cycle(schedule, schedule.next_run_date) <= today:
            schedule.next_run_date = next_cycle(schedule, schedule.next_run_date)
        # An end date before the next bill would quietly end the schedule.
        if schedule.end_date and schedule.end_date < schedule.next_run_date:
            raise AppError("The end date must be on or after the next due date", "RECURRING_COST_END_BEFORE_NEXT", 422)
        await self.db.flush()
        await self.make_due(schedule, today)
        return schedule

    async def set_active(self, schedule_id: uuid.UUID, active: bool, today: date) -> RecurringCost:
        schedule = await self.get(schedule_id, lock=True)
        schedule.active = active
        if active:
            # Resuming skips the cycles missed while paused.
            while schedule.next_run_date < today:
                schedule.next_run_date = next_cycle(schedule, schedule.next_run_date)
            await self.make_due(schedule, today)
        await self.db.flush()
        return schedule

    async def delete(self, schedule_id: uuid.UUID) -> None:
        schedule = await self.get(schedule_id, lock=True)
        await self.db.delete(schedule)  # its bills stay, unlinked
        await self.db.flush()

    async def make_due(self, schedule: RecurringCost, today: date) -> list[Cost]:
        """Makes the bills for every cycle due within LEAD_DAYS of today."""
        made: list[Cost] = []
        schedule = await self.get(schedule.id, lock=True)
        horizon = today + timedelta(days=LEAD_DAYS)
        while schedule.active and schedule.next_run_date <= horizon and len(made) < MAX_CATCH_UP:
            cycle = schedule.next_run_date
            if schedule.end_date and cycle > schedule.end_date:
                schedule.active = False
                break
            exists = await self.db.scalar(select(Cost.id).where(Cost.recurring_cost_id == schedule.id, Cost.recurrence_date == cycle))
            if not exists:
                bill = Cost(
                    description=schedule.description,
                    category=schedule.category,
                    amount=schedule.amount,
                    due_date=cycle,
                    status="due",
                    supplier_id=schedule.supplier_id,
                    notes=schedule.notes,
                    recurring_cost_id=schedule.id,
                    recurrence_date=cycle,
                    created_by=schedule.created_by,
                )
                self.db.add(bill)
                made.append(bill)
            schedule.next_run_date = next_cycle(schedule, cycle)
            if schedule.end_date and schedule.next_run_date > schedule.end_date:
                schedule.active = False
        await self.db.flush()
        return made

    async def make_all_due(self, today: date) -> int:
        ids = await self.db.scalars(
            select(RecurringCost.id).where(RecurringCost.active.is_(True), RecurringCost.next_run_date <= today + timedelta(days=LEAD_DAYS))
        )
        count = 0
        for schedule_id in ids.all():
            count += len(await self.make_due(await self.get(schedule_id), today))
        return count
