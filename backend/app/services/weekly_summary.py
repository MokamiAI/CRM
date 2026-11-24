"""The Monday summary email: last week in a few lines, and what's coming.

Sent at 07:00 on Mondays (celery_app.conf.beat_schedule, "weekly-summary")
to everyone who gets it: the account owner by default, anyone else who
switched it on in their profile (and the owner can switch it off). Skipped
for a company with nothing to report, a suspended one, and one whose plan
has run out. Recorded behind the bell too, once per person per week.
"""
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models.customer import Customer
from app.models.enums import InvoiceStatus, QuoteStatus
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.quote import Quote
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services import platform_email
from app.services.forecast_service import ForecastService
from app.services.notify import notify

logger = logging.getLogger(__name__)

_SENT = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.OVERDUE)
_OPEN = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)
_ZERO = Decimal("0")


def _money(currency: str, amount) -> str:
    return f"{currency} {Decimal(amount):,.0f}" if Decimal(amount) == Decimal(amount).to_integral() else f"{currency} {Decimal(amount):,.2f}"


class WeeklySummary:
    """Acts for one company: the session must be scoped to it."""

    def __init__(self, db):
        self.db = db

    async def figures(self, today: date, tz: str) -> dict:
        start, end = today - timedelta(days=7), today - timedelta(days=1)
        zone = ZoneInfo(tz)
        since = datetime.combine(start, time.min, zone)
        until = datetime.combine(today, time.min, zone)
        paid = (await self.db.execute(select(func.coalesce(func.sum(Payment.amount), 0), func.count()).where(Payment.paid_at >= since, Payment.paid_at < until))).one()
        invoiced = (
            await self.db.execute(
                select(func.coalesce(func.sum(Invoice.total), 0), func.count()).where(Invoice.status.in_(_SENT), Invoice.issue_date >= start, Invoice.issue_date <= end)
            )
        ).one()
        quoted = (
            await self.db.execute(
                select(func.coalesce(func.sum(Quote.total), 0), func.count()).where(Quote.status != QuoteStatus.DRAFT, Quote.issue_date >= start, Quote.issue_date <= end)
            )
        ).one()
        waiting = (await self.db.execute(select(func.coalesce(func.sum(Quote.total), 0), func.count()).where(Quote.status == QuoteStatus.SENT))).one()
        owed_rows = (
            await self.db.execute(
                select(Customer.name, Invoice.due_date, Invoice.balance_due).join(Customer, Customer.id == Invoice.customer_id).where(Invoice.status.in_(_OPEN))
            )
        ).all()
        owed = sum((Decimal(r[2]) for r in owed_rows if r[2] > 0), _ZERO)
        overdue_by: dict[str, Decimal] = {}
        for name, due, balance in owed_rows:
            if balance > 0 and due < today:
                overdue_by[name] = overdue_by.get(name, _ZERO) + Decimal(balance)
        return {
            "start": start, "end": end,
            "paid": Decimal(paid[0]), "payments": paid[1],
            "invoiced": Decimal(invoiced[0]), "invoices": invoiced[1],
            "quoted": Decimal(quoted[0]), "quotes": quoted[1],
            "waiting": Decimal(waiting[0]), "waiting_count": waiting[1],
            "owed": owed, "overdue": sum(overdue_by.values(), _ZERO), "overdue_customers": len(overdue_by),
            "top_overdue": sorted(overdue_by.items(), key=lambda item: -item[1])[:3],
        }

    @staticmethod
    def worth_sending(f: dict) -> bool:
        return bool(f["payments"] or f["invoices"] or f["quotes"] or f["owed"] > 0 or f["waiting_count"])

    async def email_for(self, person: User, company, f: dict, forecast: dict):
        currency = (company.default_currency or "ZAR").upper()
        m = lambda amount: _money(currency, amount)  # noqa: E731
        week = f"{f['start']:%d %b} to {f['end']:%d %b}"
        details = [
            ("Paid to you", f"{m(f['paid'])} ({f['payments']} payment{'s' if f['payments'] != 1 else ''})"),
            ("Invoiced", f"{m(f['invoiced'])} ({f['invoices']} invoice{'s' if f['invoices'] != 1 else ''})"),
            ("Quotes sent", f"{m(f['quoted'])} ({f['quotes']})"),
            ("Owed to you now", m(f["owed"])),
            ("Of that, overdue", f"{m(f['overdue'])} ({f['overdue_customers']} customer{'s' if f['overdue_customers'] != 1 else ''})"),
        ]
        if f["waiting_count"]:
            details.append(("Quotes awaiting an answer", f"{m(f['waiting'])} ({f['waiting_count']})"))
        coming = forecast["windows"][0]
        details.append(("Next 30 days, coming in", m(coming["money_in"])))
        if forecast["includes_costs"]:
            details.append(("Next 30 days, going out", m(coming["money_out"])))
        paragraphs = [f"Hi {person.full_name.split(' ')[0]},", f"Here is your week at {company.company_name}, {week}."]
        if f["top_overdue"]:
            names = ", ".join(f"{name} ({m(amount)})" for name, amount in f["top_overdue"])
            paragraphs.append(f"Worth a call this week: {names}.")
        if forecast["includes_costs"] and Decimal(coming["net"]) < 0:
            paragraphs.append("More is due out than in over the next 30 days. Chasing what's owed now helps close the gap.")
        return platform_email.compose(
            to=person.email,
            subject=f"Your week at {company.company_name}: {m(f['paid'])} paid in",
            title=f"Your week: {week}",
            paragraphs=paragraphs,
            details=details,
            button=("Open YGT", platform_email.app_link("/")),
            after=["You get this every Monday. To stop it, untick \"Monday summary email\" in your profile in YGT."],
        )

    async def send(self, today: date) -> int:
        """Sends this company's summaries; returns how many went out."""
        from app.services.billing_service import BillingService

        company = await CompanySettingsRepository(self.db).get_current()
        if company.suspended_at is not None or (await BillingService(self.db).current()).locked:
            return 0
        people = [u for u in (await self.db.scalars(select(User))).all() if u.gets_weekly_summary and u.email_verified_at is not None]
        if not people:
            return 0
        f = await self.figures(today, company.default_timezone)
        if not self.worth_sending(f):
            return 0
        sent = 0
        currency = (company.default_currency or "ZAR").upper()
        for person in people:
            note = await notify(
                self.db, person, kind="weekly_summary", title=f"Your week: {_money(currency, f['paid'])} paid in, {_money(currency, f['overdue'])} overdue",
                link="/", key=f"weekly-summary:{today.isoformat()}", email=False,
            )
            if note is None:
                continue  # already sent this week
            forecast = await ForecastService(self.db).forecast(today, include_costs=person.can_view_costs)
            await platform_email.queue(self.db, await self.email_for(person, company, f, forecast))
            sent += 1
        return sent


async def send_all(today_utc: date | None = None) -> int:
    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system, set_tenant
    from app.services.reminder_service import company_today

    async with AsyncSessionLocal() as db:
        set_system(db)
        company_ids = await CompanySettingsRepository(db).list_ids()
    total = 0
    for company_id in company_ids:
        try:
            async with AsyncSessionLocal() as db:
                set_tenant(db, company_id)
                company = await CompanySettingsRepository(db).get_current()
                today = today_utc or company_today(company.default_timezone)
                total += await WeeklySummary(db).send(today)
                await db.commit()
        except Exception:
            logger.exception("Weekly summary failed for company %s", company_id)
    return total
