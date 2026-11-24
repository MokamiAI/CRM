"""Cash forecast: what should come in and go out over the next 30, 60 and
90 days, so an owner sees a crunch coming before it hits.

Money in:  what's still owed on sent invoices, on their due dates; plus the
           invoices repeating invoices will make, on their due dates.
Money out: bills (costs) still to pay, on their due dates; plus the bills
           repeating costs will make. A cycle that already became a bill
           is counted once, as that bill.
Overdue money is shown on its own: it's owed, but not when.
No bank feed: the figures come from what's in YGT.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.cost import Cost, RecurringCost
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.recurring import RecurringInvoice
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.recurring_service import next_cycle, schedule_total

WINDOWS = (30, 60, 90)
HORIZON = max(WINDOWS)
_OPEN = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)
_ZERO = Decimal("0")


def _cycles(schedule, until: date) -> list[date]:
    """The schedule's coming cycles, from its next run up to `until`."""
    out: list[date] = []
    cycle = schedule.next_run_date
    while cycle <= until and (schedule.end_date is None or cycle <= schedule.end_date) and len(out) < 120:
        out.append(cycle)
        cycle = next_cycle(schedule, cycle)
    return out


class ForecastService:
    """Acts for one company: the session must be scoped to it."""

    def __init__(self, db):
        self.db = db

    async def forecast(self, today: date, include_costs: bool) -> dict:
        until = today + timedelta(days=HORIZON)
        money_in: list[tuple[date, Decimal]] = []
        money_out: list[tuple[date, Decimal]] = []
        overdue_in = overdue_out = _ZERO
        overdue_in_count = overdue_out_count = 0

        invoices = (await self.db.execute(select(Invoice.due_date, Invoice.balance_due).where(Invoice.status.in_(_OPEN)))).all()
        for due, balance in invoices:
            owed = Decimal(balance)
            if owed <= 0:
                continue
            if due < today:
                overdue_in += owed
                overdue_in_count += 1
            else:
                money_in.append((due, owed))

        terms = (await CompanySettingsRepository(self.db).get_current()).payment_terms_days or 30
        for schedule in (await self.db.scalars(select(RecurringInvoice).where(RecurringInvoice.active.is_(True)))).all():
            total = schedule_total(schedule)
            for cycle in _cycles(schedule, until):
                money_in.append((cycle + timedelta(days=schedule.due_days if schedule.due_days is not None else terms), total))

        if include_costs:
            made: set[tuple] = set()
            for due, amount, recurring_id, recurrence in (
                await self.db.execute(select(Cost.due_date, Cost.amount, Cost.recurring_cost_id, Cost.recurrence_date).where(Cost.status == "due"))
            ).all():
                if recurring_id:
                    made.add((recurring_id, recurrence))
                if due < today:
                    overdue_out += Decimal(amount)
                    overdue_out_count += 1
                else:
                    money_out.append((due, Decimal(amount)))
            # Paid ones too: a cycle paid early isn't owed again.
            made |= {
                (rid, when)
                for rid, when in (await self.db.execute(select(Cost.recurring_cost_id, Cost.recurrence_date).where(Cost.recurring_cost_id.is_not(None)))).all()
            }
            for schedule in (await self.db.scalars(select(RecurringCost).where(RecurringCost.active.is_(True)))).all():
                for cycle in _cycles(schedule, until):
                    if (schedule.id, cycle) not in made:
                        money_out.append((cycle, Decimal(schedule.amount)))

        def within(rows, days):
            end = today + timedelta(days=days)
            return sum((amount for when, amount in rows if today <= when <= end), _ZERO)

        windows = []
        for days in WINDOWS:
            coming_in, going_out = within(money_in, days), within(money_out, days)
            windows.append({"days": days, "money_in": coming_in, "money_out": going_out, "net": coming_in - going_out})
        return {
            "as_of": today,
            "includes_costs": include_costs,
            "overdue_in": overdue_in,
            "overdue_in_count": overdue_in_count,
            "overdue_out": overdue_out,
            "overdue_out_count": overdue_out_count,
            "windows": windows,
        }
