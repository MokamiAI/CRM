"""Sign-ups, payments and ended trials move through YGT's own pipeline."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.plans import PLANS
from app.core.tenancy import set_system
from app.models.billing import SubscriberLink, Subscription
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import DealStage
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
