"""Reporting: the numbers behind the sales dashboard and the enriched
customer list. Aggregated in SQL, so they don't depend on the 200-row
list cap the client-side dashboard used to compute from."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Activity, Contact, Deal, Note
from app.models.customer import Customer
from app.models.enums import OPEN_DEAL_STAGES, DealStage, InvoiceStatus
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.reminder_service import company_today

OPEN_INVOICE = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)
ZERO = Decimal("0")
# Aged receivables: days past the due date, oldest last.
AGE_BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_90_plus")


def _month_start(d: date, back: int = 0) -> date:
    year, month = d.year, d.month - back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summary(self) -> dict:
        settings_row = await CompanySettingsRepository(self.db).get_current()
        today = company_today(settings_row.default_timezone)
        month_start = _month_start(today)
        balance = Invoice.total - Invoice.amount_paid

        # Pipeline by stage (open stages only, in board order).
        rows = await self.db.execute(
            select(Deal.stage, func.count(), func.coalesce(func.sum(Deal.value), 0))
            .where(Deal.stage.in_(OPEN_DEAL_STAGES))
            .group_by(Deal.stage)
        )
        by_stage = {stage: (count, value) for stage, count, value in rows.all()}
        pipeline = [
            {"stage": s.value, "count": by_stage.get(s, (0, ZERO))[0], "value": by_stage.get(s, (0, ZERO))[1]}
            for s in OPEN_DEAL_STAGES
        ]

        won_month = (
            await self.db.execute(
                select(func.count(), func.coalesce(func.sum(Deal.value), 0)).where(
                    Deal.stage == DealStage.WON, Deal.closed_at >= _utc(month_start)
                )
            )
        ).one()

        # Win rate over the last 90 days of closed deals.
        closed = (
            await self.db.execute(
                select(
                    func.count().filter(Deal.stage == DealStage.WON),
                    func.count().filter(Deal.stage == DealStage.LOST),
                ).where(Deal.closed_at >= _utc(today - timedelta(days=90)))
            )
        ).one()
        decided = closed[0] + closed[1]
        win_rate = round(closed[0] / decided, 3) if decided else None

        avg_won = (await self.db.execute(select(func.avg(Deal.value)).where(Deal.stage == DealStage.WON))).scalar()

        receivables = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(balance), 0),
                    func.coalesce(func.sum(balance).filter(Invoice.status == InvoiceStatus.OVERDUE), 0),
                    func.count(),
                ).where(Invoice.status.in_(OPEN_INVOICE))
            )
        ).one()

        # Cash collected per month, last 6 months, oldest first; empty
        # months included so the chart's x-axis is continuous.
        first = _month_start(today, 5)
        # Bucket by the company's calendar month. date_trunc on a timestamptz
        # works in the DB session's timezone and hands back an instant, so a
        # payment on 2 Oct could land in "September" once read back as UTC.
        # Converting to local wall-clock time first makes the month exact.
        local_paid = func.timezone(settings_row.default_timezone, Payment.paid_at)
        month_col = func.date_trunc("month", local_paid)
        rows = await self.db.execute(
            select(month_col, func.sum(Payment.amount)).where(Payment.paid_at >= _utc(first)).group_by(month_col)
        )
        collected_map = {m.date(): total for m, total in rows.all()}
        collected = [
            {"month": _month_start(today, back).isoformat(), "total": collected_map.get(_month_start(today, back), ZERO)}
            for back in range(5, -1, -1)
        ]

        top = (
            await self.db.execute(
                select(Deal, Customer.name)
                .join(Customer, Customer.id == Deal.customer_id)
                .where(Deal.stage.in_(OPEN_DEAL_STAGES))
                .order_by(Deal.value.desc())
                .limit(5)
            )
        ).all()

        return {
            "pipeline": pipeline,
            "open_pipeline_value": sum((p["value"] for p in pipeline), ZERO),
            "open_deal_count": sum(p["count"] for p in pipeline),
            "won_this_month": {"count": won_month[0], "value": won_month[1]},
            "win_rate": win_rate,
            "avg_won_deal": avg_won,
            "outstanding": receivables[0],
            "overdue": receivables[1],
            "open_invoice_count": receivables[2],
            "collected_by_month": collected,
            "top_deals": [
                {"id": d.id, "title": d.title, "customer_id": d.customer_id, "customer_name": name, "stage": d.stage.value, "value": d.value, "owner_id": d.owner_id}
                for d, name in top
            ],
            "recent_activity": await self._recent_activity(),
        }

    async def _recent_activity(self, limit: int = 8) -> list[dict]:
        """A cross-customer feed: what happened lately, newest first."""
        items: list[dict] = []
        names = dict((await self.db.execute(select(Customer.id, Customer.name))).all())

        for n in (await self.db.execute(select(Note).order_by(Note.created_at.desc()).limit(limit))).scalars():
            items.append({"kind": "note", "at": n.created_at, "title": "Note added", "detail": n.body, "customer_id": n.customer_id, "deal_id": n.deal_id, "actor_id": n.author_id})
        for a in (
            await self.db.execute(select(Activity).where(Activity.done.is_(True)).order_by(Activity.done_at.desc()).limit(limit))
        ).scalars():
            items.append({"kind": "activity", "at": a.done_at, "title": f"{a.type.value.capitalize()} completed", "detail": a.subject, "params": {"type": a.type.value}, "customer_id": a.customer_id, "deal_id": a.deal_id, "actor_id": a.owner_id})
        for p, number, customer_id in (
            await self.db.execute(
                select(Payment, Invoice.invoice_number, Invoice.customer_id)
                .join(Invoice, Invoice.id == Payment.invoice_id)
                .order_by(Payment.paid_at.desc())
                .limit(limit)
            )
        ).all():
            items.append({"kind": "payment", "at": p.paid_at, "title": "Payment received", "detail": number, "params": {"number": number, "amount": str(p.amount)}, "customer_id": customer_id, "invoice_id": p.invoice_id, "actor_id": p.recorded_by})
        for d in (
            await self.db.execute(select(Deal).where(Deal.closed_at.is_not(None)).order_by(Deal.closed_at.desc()).limit(limit))
        ).scalars():
            items.append({"kind": f"deal_{d.stage.value}", "at": d.closed_at, "title": f"Deal {d.stage.value}", "detail": d.title, "customer_id": d.customer_id, "deal_id": d.id, "actor_id": d.owner_id})

        items.sort(key=lambda i: i["at"], reverse=True)
        for item in items:
            item["customer_name"] = names.get(item["customer_id"])
        return items[:limit]

    async def aged_receivables(self) -> dict:
        """Everything still owed on sent invoices, per customer, by how many
        days past due it is on the company's own calendar: not yet due,
        1-30, 31-60, 61-90 and over 90 days."""
        settings_row = await CompanySettingsRepository(self.db).get_current()
        today = company_today(settings_row.default_timezone)
        balance = Invoice.total - Invoice.amount_paid
        late = literal(today) - Invoice.due_date  # whole days in PostgreSQL
        bucket = case(
            (late <= 0, "current"),
            (late <= 30, "days_1_30"),
            (late <= 60, "days_31_60"),
            (late <= 90, "days_61_90"),
            else_="days_90_plus",
        )
        rows = await self.db.execute(
            select(Customer.id, Customer.name, bucket, func.sum(balance), func.count(), func.max(late))
            .join(Customer, Customer.id == Invoice.customer_id)
            .where(Invoice.status.in_(OPEN_INVOICE), balance > 0)
            .group_by(Customer.id, Customer.name, bucket)
        )
        customers: dict = {}
        totals = {b: ZERO for b in AGE_BUCKETS}
        for customer_id, name, age, amount, count, most_late in rows.all():
            row = customers.setdefault(
                customer_id,
                {"customer_id": customer_id, "customer_name": name, "invoices": 0, "oldest_days_late": 0, **{b: ZERO for b in AGE_BUCKETS}},
            )
            row[age] += amount
            row["invoices"] += count
            row["oldest_days_late"] = max(row["oldest_days_late"], int(most_late))
            totals[age] += amount
        for row in customers.values():
            row["total"] = sum((row[b] for b in AGE_BUCKETS), ZERO)
        # Who to call first: the most money furthest overdue.
        ordered = sorted(customers.values(), key=lambda r: (-(r["total"] - r["current"]), -r["total"]))
        return {"as_of": today, "totals": {**totals, "total": sum(totals.values(), ZERO)}, "customers": ordered}

    async def customer_overview(self, search: str | None = None, is_active: bool | None = None) -> list[dict]:
        """Customers with the columns a CRM list shows: primary contact,
        open deals and their value, balance owed, last touchpoint."""
        primary = (
            select(func.concat_ws(" ", Contact.first_name, Contact.last_name))
            .where(Contact.customer_id == Customer.id, Contact.is_primary.is_(True))
            .limit(1)
            .scalar_subquery()
        )
        open_deals = (
            select(func.count()).where(Deal.customer_id == Customer.id, Deal.stage.in_(OPEN_DEAL_STAGES)).scalar_subquery()
        )
        pipeline = (
            select(func.coalesce(func.sum(Deal.value), 0))
            .where(Deal.customer_id == Customer.id, Deal.stage.in_(OPEN_DEAL_STAGES))
            .scalar_subquery()
        )
        owed = (
            select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0))
            .where(Invoice.customer_id == Customer.id, Invoice.status.in_(OPEN_INVOICE))
            .scalar_subquery()
        )
        overdue = (
            select(func.count())
            .where(Invoice.customer_id == Customer.id, Invoice.status == InvoiceStatus.OVERDUE)
            .scalar_subquery()
        )
        last_touch = func.greatest(
            select(func.max(Note.created_at)).where(Note.customer_id == Customer.id).scalar_subquery(),
            select(func.max(Activity.done_at)).where(Activity.customer_id == Customer.id).scalar_subquery(),
            select(func.max(Invoice.created_at)).where(Invoice.customer_id == Customer.id).scalar_subquery(),
            select(func.max(Payment.paid_at))
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(Invoice.customer_id == Customer.id)
            .scalar_subquery(),
        )
        stmt = select(Customer, primary, open_deals, pipeline, owed, overdue, last_touch)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(or_(Customer.name.ilike(pattern), Customer.email.ilike(pattern)))
        if is_active is not None:
            stmt = stmt.where(Customer.is_active == is_active)
        rows = await self.db.execute(stmt.order_by(Customer.name).limit(200))
        return [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "is_active": c.is_active,
                "primary_contact": contact,
                "open_deals": deals,
                "pipeline_value": value,
                "balance": balance,
                "overdue_invoices": overdue_count,
                "last_activity_at": last,
            }
            for c, contact, deals, value, balance, overdue_count, last in rows.all()
        ]

