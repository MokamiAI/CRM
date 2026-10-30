"""Agreeing to the terms is required and recorded (ECTA), and yearly plans
are told before they renew (CPA s14)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.legal import TERMS_VERSION
from app.core.tenancy import set_system
from app.models.billing import Subscription
from app.models.user import User
from app.tasks.billing_tasks import send_renewal_notices
from .conftest import ADDRESS, new_company


async def _user(email):
    async with AsyncSessionLocal() as db:
        set_system(db)
        return await db.scalar(select(User).where(User.email == email))


@pytest.mark.asyncio
@pytest.mark.parametrize("agreed", [None, False])
async def test_an_account_needs_the_terms_agreed(api, agreed):
    body = {"company_name": "No Terms Co", "full_name": "Owner", "email": f"{uuid.uuid4().hex[:12]}@example.com",
            "password": "Correct-Horse-9", "business_address": ADDRESS}
    if agreed is not None:
        body["accept_terms"] = agreed
    assert (await api.post("/auth/register", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_the_agreement_is_recorded_with_its_version(api):
    owner = await new_company(api, "Terms Co")
    user = await _user(owner["email"])
    assert user.terms_version == TERMS_VERSION and user.terms_accepted_at is not None


async def _yearly(company_id, renews_in_days, status="active", interval="annually"):
    async with AsyncSessionLocal() as db:
        set_system(db)
        sub = await db.scalar(select(Subscription).where(Subscription.company_id == company_id))
        sub.status, sub.interval, sub.plan, sub.seats = status, interval, "grow", 2
        sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=renews_in_days)
        sub.renewal_notice_for = None
        await db.commit()


def _notices(api, before, email):
    return [args[0] for name, args in api.queued[before:]
            if name.endswith("send_platform_email_task") and args[0]["to"] == email and "renews" in args[0]["subject"]]


@pytest.mark.asyncio
async def test_a_yearly_plan_hears_once_inside_the_window(api):
    owner = await new_company(api, "Renewal Co")
    others = [await new_company(api, f"Renewal other {i}") for i in range(3)]
    await _yearly(owner["company_id"], 80)
    await _yearly(others[0]["company_id"], 30)  # too late to be in the window
    await _yearly(others[1]["company_id"], 80, interval="monthly")  # not a fixed term
    await _yearly(others[2]["company_id"], 80, status="cancelled")  # won't renew

    before = len(api.queued)
    await send_renewal_notices()
    [notice] = _notices(api, before, owner["email"])
    assert "R4 580.00" in notice["text"] and "Settings > Billing" in notice["text"]
    assert not any(_notices(api, before, o["email"]) for o in others)

    before = len(api.queued)
    await send_renewal_notices()  # the next day: not again for the same year
    assert not _notices(api, before, owner["email"])
