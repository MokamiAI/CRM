"""The dashboard's figures come from the company's own records: customers,
money invoiced and collected per month, and nothing from other companies."""
from datetime import date
from decimal import Decimal

import pytest

from .conftest import new_company

ITEM = [{"description": "Platter", "quantity": "2", "unit_price": "500", "tax_rate": "15"}]  # 1 150.00


@pytest.mark.asyncio
async def test_summary_counts_customers_and_money_by_month(api):
    owner = await new_company(api, "Upsilon Events")
    h = owner["headers"]
    a = (await api.post("/customers", json={"name": "A"}, headers=h)).json()
    b = (await api.post("/customers", json={"name": "B"}, headers=h)).json()
    await api.post(f"/customers/{b['id']}/deactivate", headers=h)

    today = date.today().isoformat()
    sent = (await api.post("/invoices", json={"customer_id": a["id"], "issue_date": today, "items": ITEM}, headers=h)).json()
    await api.post(f"/invoices/{sent['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/invoices/{sent['id']}/payments", json={"amount": "400.00", "method": "eft"}, headers=h)
    await api.post("/invoices", json={"customer_id": a["id"], "issue_date": today, "items": ITEM}, headers=h)  # draft: not invoiced yet

    s = (await api.get("/reports/summary", headers=h)).json()
    assert s["active_customers"] == 1 and s["new_customers_this_month"] == 1
    assert len(s["invoiced_by_month"]) == 12 and len(s["collected_by_month"]) == 12
    assert s["invoiced_by_month"][-1]["month"] == date.today().replace(day=1).isoformat()
    assert Decimal(s["invoiced_by_month"][-1]["total"]) == Decimal("1150.00")
    assert Decimal(s["collected_by_month"][-1]["total"]) == Decimal("400.00")
    assert all(Decimal(m["total"]) == 0 for m in s["invoiced_by_month"][:-1])

    other = (await api.get("/reports/summary", headers=(await new_company(api, "Phi Florists"))["headers"])).json()
    assert other["active_customers"] == 0 and Decimal(other["invoiced_by_month"][-1]["total"]) == 0
