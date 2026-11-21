"""The cash forecast: what's owed comes in on its due date, overdue money
stands apart, repeating invoices and bills are counted once, and money out
is shown only to people who may see costs."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from .conftest import new_company


def _day(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


async def _invoice(api, h, customer_id, amount, due_in, send=True):
    res = await api.post("/invoices", json={"customer_id": customer_id, "issue_date": _day(min(due_in, 0) - 5), "due_date": _day(due_in),
                                            "items": [{"description": "Work", "quantity": "1", "unit_price": amount, "tax_rate": "0"}]}, headers=h)
    assert res.status_code == 201, res.text
    if send:
        assert (await api.post(f"/invoices/{res.json()['id']}/send", params={"notify": "false"}, headers=h)).status_code == 200
    return res.json()


def _money(window):
    return {k: Decimal(str(window[k])) for k in ("money_in", "money_out", "net")}


@pytest.mark.asyncio
async def test_money_in_and_out_over_the_next_90_days(api):
    owner = await new_company(api, "Forecast Flooring")
    h = owner["headers"]
    c = (await api.post("/customers", json={"name": "Client"}, headers=h)).json()["id"]
    await _invoice(api, h, c, "1000", 10)            # in within 30
    part = await _invoice(api, h, c, "2000", 45)     # 31-60, part paid
    assert (await api.post(f"/invoices/{part['id']}/payments", json={"amount": "500", "method": "eft"}, headers=h)).status_code == 201
    await _invoice(api, h, c, "700", -5)             # overdue: on its own
    await _invoice(api, h, c, "999", 5, send=False)  # draft: not counted
    await _invoice(api, h, c, "4000", 200)           # beyond 90 days

    # A monthly repeating invoice from next week, due 7 days after each one.
    res = await api.post("/recurring-invoices", json={"customer_id": c, "frequency": "monthly", "start_date": _day(7), "due_days": 7,
                                                      "items": [{"description": "Retainer", "quantity": "1", "unit_price": "300", "tax_rate": "0"}]}, headers=h)
    assert res.status_code == 201, res.text

    # A bill due in 20 days, and a monthly repeating cost from tomorrow.
    assert (await api.post("/costs", json={"description": "Rent", "category": "Rent", "amount": "400", "due_date": _day(20)}, headers=h)).status_code == 201, "cost"
    res = await api.post("/recurring-costs", json={"description": "Software", "category": "Software", "amount": "100", "frequency": "monthly", "start_date": _day(1)}, headers=h)
    assert res.status_code == 201, res.text

    f = (await api.get("/reports/cash-forecast", headers=h)).json()
    assert Decimal(str(f["overdue_in"])) == Decimal("700") and f["overdue_in_count"] == 1 and f["includes_costs"] is True
    w30, w60, w90 = (_money(w) for w in f["windows"])
    # 30 days: 1000 + the first retainer (day 7 + 7 = 14) + maybe the second (day 37+7 = 44, no).
    assert w30["money_in"] == Decimal("1300")
    # Out within 30: rent 400, plus software once or twice (made a week ahead counts once).
    assert w30["money_out"] in (Decimal("500"), Decimal("600"))
    assert w60["money_in"] == Decimal("1300") + Decimal("1500") + Decimal("300")
    assert w90["money_in"] >= w60["money_in"] and w90["money_in"] < Decimal("4000")
    assert w90["net"] == w90["money_in"] - w90["money_out"]


@pytest.mark.asyncio
async def test_money_out_is_hidden_from_people_who_cannot_see_costs(api):
    owner = await new_company(api, "Private Plumbing")
    h = owner["headers"]
    from sqlalchemy import update

    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system
    from app.models.user import User

    assert (await api.post("/costs", json={"description": "Rent", "category": "Rent", "amount": "400", "due_date": _day(5)}, headers=h)).status_code == 201
    async with AsyncSessionLocal() as db:  # as if the owner were a manager without cost access
        set_system(db)
        await db.execute(update(User).where(User.id == owner["user_id"]).values(is_account_owner=False, cost_access="none"))
        await db.commit()
    f = (await api.get("/reports/cash-forecast", headers=h)).json()
    assert f["includes_costs"] is False and all(Decimal(str(w["money_out"])) == 0 for w in f["windows"])
