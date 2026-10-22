"""Sign-ups, payments and ended trials move through YGT's own pipeline."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.plans import PLANS
from app.core.tenancy import set_system
from app.models.billing import BillingPayment, SubscriberLink, Subscription
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import DealStage, InvoiceStatus, QuoteStatus, UserRole
from app.models.invoice import Invoice
from app.models.quote import Quote
from app.models.recurring import RecurringInvoice
from app.models.user import User
from app.services import subscriber_pipeline
from .conftest import new_company


async def sync(*company_ids):
    async with AsyncSessionLocal() as db:
        changes = await subscriber_pipeline.sync(db, only=set(company_ids))
        await db.commit()
    return changes


async def pipeline(ygt, company_id):
    async with AsyncSessionLocal() as db:
        set_system(db)
        link = await db.get(SubscriberLink, company_id)
        if link is None:
            return None, None, None
        deal = await db.get(Deal, link.deal_id) if link.deal_id else None
        customer = await db.get(Customer, link.customer_id) if link.customer_id else None
        assert customer is None or customer.company_id == ygt["company_id"]
        return link, deal, customer


async def set_subscription(company_id, **values):
    async with AsyncSessionLocal() as db:
        set_system(db)
        sub = await db.scalar(select(Subscription).where(Subscription.company_id == company_id))
        for field, value in values.items():
            setattr(sub, field, value)
        await db.commit()


@pytest_asyncio.fixture
async def ygt(api, monkeypatch):
    owner = await new_company(api, "YGT Pipeline HQ")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", owner["email"])
    return owner


@pytest.mark.asyncio
async def test_a_trial_becomes_a_negotiation_then_a_customer_then_a_proposal(api, ygt):
    subscriber = await new_company(api, "Pipeline Subscriber Co", plan="scale")
    changes = await sync(subscriber["company_id"])
    assert [(c.action, c.stage) for c in changes] == [("add", DealStage.NEGOTIATION)]
    link, deal, customer = await pipeline(ygt, subscriber["company_id"])
    assert customer.name == "Pipeline Subscriber Co" and customer.is_prospect
    assert customer.email == subscriber["email"]
    assert deal.stage == DealStage.NEGOTIATION and deal.value == Decimal(PLANS["scale"].price_cents("monthly", 1)) / 100
    assert deal.expected_close_date is not None and deal.owner_id == ygt["user_id"]

    assert await sync(subscriber["company_id"]) == []  # nothing new: no second prospect or deal

    now = datetime.now(timezone.utc)
    await set_subscription(subscriber["company_id"], status="active", seats=3, trial_ends_at=None, current_period_end=now + timedelta(days=30))
    assert [c.stage for c in await sync(subscriber["company_id"])] == [DealStage.WON]
    link, won, customer = await pipeline(ygt, subscriber["company_id"])
    assert won.id == deal.id and won.stage == DealStage.WON and not customer.is_prospect
    assert won.value == Decimal(PLANS["scale"].price_cents("monthly", 3)) / 100

    await set_subscription(subscriber["company_id"], current_period_end=now - timedelta(days=10))
    assert [c.stage for c in await sync(subscriber["company_id"])] == [DealStage.PROPOSAL]
    link, lapsed, _ = await pipeline(ygt, subscriber["company_id"])
    assert lapsed.stage == DealStage.PROPOSAL and link.state == "lapsed"


@pytest.mark.asyncio
async def test_a_stage_set_by_hand_stays_until_the_subscription_changes(api, ygt):
    subscriber = await new_company(api, "Hand Moved Co")
    await sync(subscriber["company_id"])
    _, deal, _ = await pipeline(ygt, subscriber["company_id"])
    moved = await api.patch(f"/deals/{deal.id}", headers=ygt["headers"], json={"stage": "qualified"})
    assert moved.status_code == 200, moved.text
    assert await sync(subscriber["company_id"]) == []
    _, deal, _ = await pipeline(ygt, subscriber["company_id"])
    assert deal.stage == DealStage.QUALIFIED


@pytest.mark.asyncio
async def test_a_prospect_added_by_hand_is_reused_and_ygt_itself_is_left_out(api, ygt):
    subscriber = await new_company(api, "Already Known Co")
    known = (await api.post("/prospects", headers=ygt["headers"], json={"name": "already known co"})).json()
    await sync(subscriber["company_id"], ygt["company_id"])
    link, deal, _ = await pipeline(ygt, subscriber["company_id"])
    assert str(link.customer_id) == known["id"] and deal.stage == DealStage.NEGOTIATION
    assert (await pipeline(ygt, ygt["company_id"]))[0] is None


@pytest.mark.asyncio
async def test_without_a_platform_admin_nothing_happens(api, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", "")
    subscriber = await new_company(api, "No HQ Co")
    assert await sync(subscriber["company_id"]) == []


async def documents(link):
    async with AsyncSessionLocal() as db:
        set_system(db)
        quote = await db.scalar(select(Quote).where(Quote.id == link.quote_id).options(selectinload(Quote.items)))
        invoice = await db.scalar(select(Invoice).where(Invoice.id == link.trial_invoice_id).options(selectinload(Invoice.items)))
        return quote, invoice


@pytest.mark.asyncio
async def test_sign_up_has_an_accepted_quote_and_a_free_trial_invoice_that_follow_the_seats(api, ygt):
    subscriber = await new_company(api, "Trial Paperwork Co", plan="grow")
    changes = await sync(subscriber["company_id"])
    assert changes[0].email_invoice_id is not None  # the trial invoice goes to them
    link, deal, _ = await pipeline(ygt, subscriber["company_id"])
    quote, invoice = await documents(link)
    one_seat = Decimal(PLANS["grow"].seat_cents(1)) / 100
    assert quote.status == QuoteStatus.ACCEPTED and quote.deal_id == deal.id and quote.total == one_seat
    assert invoice.status == InvoiceStatus.PAID and invoice.total == 0 and invoice.quote_id == quote.id
    assert [line.line_total for line in sorted(invoice.items, key=lambda i: i.sort_order)] == [one_seat, -one_seat]
    assert "14-day free trial" in invoice.items[0].description or "14-day free trial" in invoice.items[1].description
    assert invoice.issue_date <= deal.expected_close_date

    async with AsyncSessionLocal() as db:  # a second person joins during the trial
        set_system(db)
        db.add(User(company_id=subscriber["company_id"], email=f"two-{subscriber['email']}", password_hash="x", full_name="Second Person", role=UserRole.STAFF))
        await db.commit()
    assert [(c.action, c.detail) for c in await sync(subscriber["company_id"])] == [("seats", "1 -> 2 seats")]
    link, deal, _ = await pipeline(ygt, subscriber["company_id"])
    same_quote, same_invoice = await documents(link)
    two_seats = Decimal(PLANS["grow"].seat_cents(2)) * 2 / 100
    assert same_quote.id == quote.id and same_quote.total == two_seats
    assert same_invoice.id == invoice.id and same_invoice.total == 0 and deal.value == two_seats


@pytest.mark.asyncio
async def test_each_payment_is_a_paid_invoice_under_one_monthly_recurring_invoice(api, ygt):
    subscriber = await new_company(api, "Paying Records Co", plan="scale")
    await sync(subscriber["company_id"])
    now = datetime.now(timezone.utc)
    amount = PLANS["scale"].price_cents("monthly", 2)
    async with AsyncSessionLocal() as db:
        set_system(db)
        db.add(BillingPayment(company_id=subscriber["company_id"], reference=f"PSK_{subscriber['company_id'].hex[:8]}_1",
                              amount_cents=amount, plan="scale", interval="monthly", seats=2, paid_at=now))
        await db.commit()
    await set_subscription(subscriber["company_id"], status="active", seats=2, trial_ends_at=None, current_period_end=now + timedelta(days=30))
    assert sorted(c.action for c in await sync(subscriber["company_id"])) == ["move", "paid"]
    assert await sync(subscriber["company_id"]) == []  # recorded once
    link, deal, customer = await pipeline(ygt, subscriber["company_id"])
    assert deal.stage == DealStage.WON and not customer.is_prospect

    async with AsyncSessionLocal() as db:  # a month later, Paystack charges again
        set_system(db)
        db.add(BillingPayment(company_id=subscriber["company_id"], reference=f"PSK_{subscriber['company_id'].hex[:8]}_2",
                              amount_cents=amount, plan="scale", interval="monthly", seats=2, paid_at=now + timedelta(days=30)))
        await db.commit()
    assert [c.action for c in await sync(subscriber["company_id"])] == ["paid"]
    async with AsyncSessionLocal() as db:
        set_system(db)
        schedule = await db.get(RecurringInvoice, link.recurring_id)
        paid = list(await db.scalars(select(Invoice).where(Invoice.recurring_invoice_id == schedule.id).order_by(Invoice.recurrence_date)))
    assert schedule.frequency == "monthly" and schedule.active
    assert [(i.status, i.total, i.amount_paid) for i in paid] == [(InvoiceStatus.PAID, Decimal(amount) / 100, Decimal(amount) / 100)] * 2
    assert paid[1].recurrence_date > paid[0].recurrence_date and schedule.next_run_date > paid[1].recurrence_date

    await set_subscription(subscriber["company_id"], current_period_end=now - timedelta(days=10))
    await sync(subscriber["company_id"])
    async with AsyncSessionLocal() as db:
        set_system(db)
        assert not (await db.get(RecurringInvoice, link.recurring_id)).active  # lapsed: no more drafts
