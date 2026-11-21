"""The Monday summary: last week's figures are right, it goes to the owner
by default and to others only if they switch it on, once a week, and not
at all for a company with nothing to report."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.payment import Payment
from app.services import platform_email
from app.services.weekly_summary import WeeklySummary

from .conftest import new_company


def _day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


async def _send(company_id, captured) -> int:
    async with AsyncSessionLocal() as db:
        set_tenant(db, company_id)
        sent = await WeeklySummary(db).send(date.today())
        await db.commit()
        return sent


@pytest.fixture
def captured(monkeypatch):
    emails = []

    async def queue(db, *messages):
        await db.commit()
        emails.extend(m for m in messages if m.subject.startswith("Your week"))  # not sign-up emails

    monkeypatch.setattr(platform_email, "queue", queue)
    return emails


@pytest.mark.asyncio
async def test_the_owner_gets_last_weeks_figures_once(api, captured):
    owner = await new_company(api, "Summary Signs")
    h, company = owner["headers"], owner["company_id"]

    # Nothing to report yet: nothing sent.
    assert await _send(company, captured) == 0 and captured == []

    c = (await api.post("/customers", json={"name": "Late Larry"}, headers=h)).json()["id"]
    paid = (await api.post("/invoices", json={"customer_id": c, "issue_date": _day(-3), "due_date": _day(10),
                                              "items": [{"description": "Sign", "quantity": "1", "unit_price": "1000", "tax_rate": "0"}]}, headers=h)).json()
    await api.post(f"/invoices/{paid['id']}/send", params={"notify": "false"}, headers=h)
    res = await api.post(f"/invoices/{paid['id']}/payments", json={"amount": "1000", "method": "eft", "paid_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}, headers=h)
    assert res.status_code == 201, res.text
    late = (await api.post("/invoices", json={"customer_id": c, "issue_date": _day(-40), "due_date": _day(-10),
                                              "items": [{"description": "Banner", "quantity": "1", "unit_price": "600", "tax_rate": "0"}]}, headers=h)).json()
    await api.post(f"/invoices/{late['id']}/send", params={"notify": "false"}, headers=h)

    assert await _send(company, captured) == 1
    [email] = captured
    assert email.to == owner["email"] and "Summary Signs" in email.subject and "ZAR 1,000 paid in" in email.subject
    assert "ZAR 1,000 (1 payment)" in email.html and "ZAR 600" in email.html and "Late Larry" in email.html
    assert "Monday summary email" in email.text  # how to stop it

    # Once a week, however often it runs.
    assert await _send(company, captured) == 0 and len(captured) == 1


@pytest.mark.asyncio
async def test_only_people_who_want_it_get_it(api, captured):
    owner = await new_company(api, "Opt Out Optics")
    h, company = owner["headers"], owner["company_id"]
    me = (await api.get("/auth/me", headers=h)).json()
    assert me["gets_weekly_summary"] is True  # the owner, by default
    c = (await api.post("/customers", json={"name": "Someone"}, headers=h)).json()["id"]
    inv = (await api.post("/invoices", json={"customer_id": c, "issue_date": _day(-2), "due_date": _day(5),
                                             "items": [{"description": "Lens", "quantity": "1", "unit_price": "100", "tax_rate": "0"}]}, headers=h)).json()
    await api.post(f"/invoices/{inv['id']}/send", params={"notify": "false"}, headers=h)

    res = await api.patch("/auth/me", json={"weekly_summary": False}, headers=h)
    assert res.status_code == 200 and res.json()["gets_weekly_summary"] is False
    assert await _send(company, captured) == 0 and captured == []

    assert (await api.patch("/auth/me", json={"weekly_summary": True}, headers=h)).json()["gets_weekly_summary"] is True
    assert await _send(company, captured) == 1
