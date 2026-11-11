"""YGT's own team runs subscriptions, not their customers' businesses: the
admin site never counts or totals a company's clients, quotes or invoices."""
import pytest

from app.core.config import settings

from .conftest import new_company

PRIVATE = {"customers", "quotes", "invoices", "invoiced", "collected"}


@pytest.mark.asyncio
async def test_admin_sees_no_company_business_figures(api, monkeypatch):
    support = await new_company(api, "YGT")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", support["email"])
    client = await new_company(api, "Private Books Co")
    assert (await api.post("/customers", json={"name": "A private client"}, headers=client["headers"])).status_code == 201

    h = support["headers"]
    listed = (await api.get("/admin/tenants", params={"search": "Private Books Co"}, headers=h)).json()
    row = next(t for t in listed if t["id"] == str(client["company_id"]))
    assert PRIVATE.isdisjoint(row), sorted(PRIVATE & set(row))
    assert row["users"] == 1 and row["plan"]

    detail = (await api.get(f"/admin/tenants/{client['company_id']}", headers=h)).json()
    assert PRIVATE.isdisjoint(detail), sorted(PRIVATE & set(detail))
    assert detail["people"][0]["email"] == client["email"]
