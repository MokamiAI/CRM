"""Aged receivables: what each customer owes on sent invoices, bucketed by
days past due, counting part-payments, ignoring drafts and paid invoices,
and never showing another company's invoices."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from .conftest import new_company


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


async def _invoice(api, headers, customer_id, amount: str, due_in: int, send: bool = True) -> dict:
    res = await api.post(
        "/invoices",
        json={
            "customer_id": customer_id,
            "issue_date": _day(min(due_in, 0) - 30),
            "due_date": _day(due_in),
            "items": [{"description": "Work", "quantity": "1", "unit_price": amount, "tax_rate": "0"}],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    invoice = res.json()
    if send:
        assert (await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=headers)).status_code == 200
    return invoice


@pytest.mark.asyncio
async def test_owed_money_is_bucketed_by_days_late(api):
    owner = await new_company(api, "Kappa Kitchens")
    h = owner["headers"]
    a = (await api.post("/customers", json={"name": "Late Payer"}, headers=h)).json()["id"]
    b = (await api.post("/customers", json={"name": "Good Payer"}, headers=h)).json()["id"]

    await _invoice(api, h, b, "1000", due_in=10)  # not yet due
    await _invoice(api, h, a, "200", due_in=-10)  # 1-30
    part = await _invoice(api, h, a, "500", due_in=-45)  # 31-60, part paid below
    await _invoice(api, h, a, "300", due_in=-75)  # 61-90
    await _invoice(api, h, a, "400", due_in=-120)  # over 90
    await _invoice(api, h, a, "999", due_in=-50, send=False)  # draft: not owed
    paid = await _invoice(api, h, b, "250", due_in=-20)  # paid in full: not owed
    assert (await api.post(f"/invoices/{part['id']}/payments", json={"amount": "150", "method": "eft"}, headers=h)).status_code == 201
    assert (await api.post(f"/invoices/{paid['id']}/payments", json={"amount": "250", "method": "cash"}, headers=h)).status_code == 201

    other = await new_company(api, "Lambda Logistics")
    c = (await api.post("/customers", json={"name": "Elsewhere"}, headers=other["headers"])).json()["id"]
    await _invoice(api, other["headers"], c, "777", due_in=-40)

    res = await api.get("/reports/aged-receivables", headers=h)
    assert res.status_code == 200, res.text
    report = res.json()
    money = lambda row: {k: Decimal(row[k]) for k in ("current", "days_1_30", "days_31_60", "days_61_90", "days_90_plus", "total")}  # noqa: E731

    assert money(report["totals"]) == {
        "current": Decimal("1000"),
        "days_1_30": Decimal("200"),
        "days_31_60": Decimal("350"),
        "days_61_90": Decimal("300"),
        "days_90_plus": Decimal("400"),
        "total": Decimal("2250"),
    }
    names = [r["customer_name"] for r in report["customers"]]
    assert names == ["Late Payer", "Good Payer"]  # most overdue first
    late = report["customers"][0]
    assert money(late)["total"] == Decimal("1250") and late["invoices"] == 4 and late["oldest_days_late"] >= 119
    good = report["customers"][1]
    assert money(good)["total"] == Decimal("1000") and money(good)["current"] == Decimal("1000")
    assert "Elsewhere" not in names
