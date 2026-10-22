"""An admin can put a paying company on a trial; their card stops first."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppError
from app.core.tenancy import set_system
from app.models.billing import Subscription
from app.services import paystack
from app.services.admin_service import AdminService
from .conftest import new_company


async def paying(api, name):
    owner = await new_company(api, name)
    async with AsyncSessionLocal() as db:
        set_system(db)
        sub = await db.scalar(select(Subscription).where(Subscription.company_id == owner["company_id"]))
        sub.status, sub.plan = "active", "scale"
        sub.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=30)
        sub.paystack_subscription_code, sub.paystack_email_token = "SUB_test", "tok_test"
        await db.commit()
    return owner["company_id"]


async def subscription(company_id):
    async with AsyncSessionLocal() as db:
        set_system(db)
        return await db.scalar(select(Subscription).where(Subscription.company_id == company_id))


@pytest.mark.asyncio
async def test_paying_company_goes_on_trial_and_its_card_subscription_stops(api, monkeypatch):
    company_id = await paying(api, "Paying To Trial Co")
    stopped = []

    async def disable(code, token):
        stopped.append((code, token))

    monkeypatch.setattr(paystack, "disable", disable)
    async with AsyncSessionLocal() as db:
        set_system(db)  # as the admin site does
        await AdminService(db).extend_trial(company_id, 14)
        await db.commit()
    assert stopped == [("SUB_test", "tok_test")]
    sub = await subscription(company_id)
    assert sub.status == "trialing" and sub.plan == "scale"
    assert sub.paystack_subscription_code is None and sub.paystack_email_token is None
    # Counted from today, not from the old trial that ended a month ago.
    assert abs((sub.trial_ends_at - datetime.now(timezone.utc)) - timedelta(days=14)) < timedelta(minutes=5)


@pytest.mark.asyncio
async def test_paying_company_stays_paid_when_paystack_cannot_stop_the_card(api, monkeypatch):
    company_id = await paying(api, "Paystack Down Co")

    async def disable(code, token):
        raise RuntimeError("Paystack unavailable")

    monkeypatch.setattr(paystack, "disable", disable)
    async with AsyncSessionLocal() as db:
        set_system(db)
        with pytest.raises(AppError):
            await AdminService(db).extend_trial(company_id, 14)
        await db.rollback()
    sub = await subscription(company_id)
    assert sub.status == "active" and sub.paystack_subscription_code == "SUB_test"
