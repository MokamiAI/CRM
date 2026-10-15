"""The annual revenue goal counts deals won this financial year (the
company picks the month it starts), and each deal shows how far it has come
from lead to client, from real activity."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.models.crm import Deal

from .conftest import new_company

ITEM = [{"description": "Catering", "quantity": "1", "unit_price": "1000", "tax_rate": "15"}]


async def _closed(deal_id, when: datetime):
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(Deal).where(Deal.id == deal_id).values(closed_at=when))
        await db.commit()


@pytest.mark.asyncio
async def test_goal_counts_deals_won_this_financial_year(api):
    owner = await new_company(api, "Goal Getters")
    h = owner["headers"]
    s = (await api.get("/reports/summary", headers=h)).json()
    assert s["goal"]["target"] is None  # not set yet

    today = date.today()
    # Year starts this month: everything from the 1st counts.
    settings = await api.patch("/settings", json={"annual_revenue_goal": "1200000", "financial_year_start_month": today.month}, headers=h)
    assert settings.status_code == 200 and Decimal(settings.json()["annual_revenue_goal"]) == Decimal("1200000")
    customer = (await api.post("/customers", json={"name": "Client"}, headers=h)).json()
    won = (await api.post("/deals", json={"title": "Big win", "customer_id": customer["id"], "stage": "won", "value": "250000"}, headers=h)).json()
    old = (await api.post("/deals", json={"title": "Last year", "customer_id": customer["id"], "stage": "won", "value": "99999"}, headers=h)).json()
    await _closed(old["id"], datetime.now(timezone.utc) - timedelta(days=400))
    await api.post("/deals", json={"title": "Still open", "customer_id": customer["id"], "stage": "proposal", "value": "50000"}, headers=h)

    g = (await api.get("/reports/summary", headers=h)).json()["goal"]
    assert Decimal(g["target"]) == Decimal("1200000")
    assert g["year_start"] == today.replace(day=1).isoformat()
    assert Decimal(g["won_value"]) == Decimal("250000") and g["won_count"] == 1
    assert won["stage"] == "won"

    bad = await api.patch("/settings", json={"financial_year_start_month": 13}, headers=h)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_goal_can_be_set_at_sign_up(api):
    import uuid

    res = await api.post("/auth/register", json={"company_name": "Goal At Signup", "full_name": "Owner", "email": f"{uuid.uuid4().hex[:10]}@example.com",
                                                  "password": "Correct-Horse-9", "annual_revenue_goal": "500000"})
    assert res.status_code == 201, res.text
    h = {"Authorization": f"Bearer {res.json()['access_token']}"}
    g = (await api.get("/reports/summary", headers=h)).json()["goal"]
    assert Decimal(g["target"]) == Decimal("500000")
    assert (await api.get("/settings", headers=h)).json()["financial_year_start_month"] == 3


@pytest.mark.asyncio
async def test_milestones_follow_real_activity(api):
    h = (await new_company(api, "Step By Step"))["headers"]
    customer = (await api.post("/customers", json={"name": "Prospect"}, headers=h)).json()
    deal = (await api.post("/deals", json={"title": "New lead", "customer_id": customer["id"]}, headers=h)).json()
    assert deal["milestones"] == ["lead"]

    call = (await api.post("/activities", json={"type": "call", "subject": "Intro call", "due_date": date.today().isoformat(), "deal_id": deal["id"]}, headers=h)).json()
    assert (await api.get(f"/deals/{deal['id']}", headers=h)).json()["milestones"] == ["lead"]  # planned, not done
    await api.patch(f"/activities/{call['id']}", json={"done": True}, headers=h)
    assert (await api.get(f"/deals/{deal['id']}", headers=h)).json()["milestones"] == ["lead", "contacted"]

    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "deal_id": deal["id"], "issue_date": date.today().isoformat(), "items": ITEM}, headers=h)).json()
    assert "quote_sent" not in (await api.get(f"/deals/{deal['id']}", headers=h)).json()["milestones"]  # a draft isn't sent
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    await api.patch(f"/deals/{deal['id']}", json={"stage": "negotiation"}, headers=h)
    m = (await api.get(f"/deals/{deal['id']}", headers=h)).json()["milestones"]
    assert m == ["lead", "contacted", "qualified", "quote_sent", "negotiation"]

    await api.patch(f"/deals/{deal['id']}", json={"stage": "won"}, headers=h)
    listed = (await api.get("/deals", params={"status": "won"}, headers=h)).json()
    assert listed[0]["milestones"][-1] == "won" and len(listed[0]["milestones"]) == 6
