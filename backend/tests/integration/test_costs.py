"""Costs: one-off and recurring bills, money in and out, and profit. Money
counts when it moves; recurring bills appear a week ahead and are never
marked paid by themselves; spending is for admins and managers only."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.models.notification import Notification
from app.services.cost_service import CostService, RecurringCostService
from sqlalchemy import select

from .conftest import mark_verified, new_company

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"
ITEM = [{"description": "Platter", "quantity": "2", "unit_price": "500", "tax_rate": "15"}]  # 1 150.00


async def company_id(api, h):
    return uuid.UUID((await api.get("/settings", headers=h)).json()["id"])


@pytest.mark.asyncio
async def test_money_in_out_and_profit_for_the_month(api):
    owner = await new_company(api, "Cost Catering")
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Dube Events"}, headers=h)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": TODAY.isoformat(), "items": ITEM}, headers=h)).json()
    await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/invoices/{invoice['id']}/payments", json={"amount": "1000.00", "method": "eft"}, headers=h)

    paid = await api.post("/costs", json={"description": "Gas bottles", "category": "stock", "amount": "350.50", "due_date": TODAY.isoformat(), "paid": True}, headers=h)
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "paid" and paid.json()["paid_date"] == TODAY.isoformat()
    bill = (await api.post("/costs", json={"description": "Electricity", "category": "utilities", "amount": "900", "due_date": (TODAY + timedelta(days=5)).isoformat()}, headers=h)).json()
    assert bill["status"] == "due" and bill["paid_date"] is None

    s = (await api.get("/costs/summary", headers=h)).json()
    assert s["month"] == MONTH
    assert Decimal(s["money_in"]) == Decimal("1000.00")
    assert Decimal(s["money_out"]) == Decimal("350.50")  # the unpaid bill doesn't count yet
    assert Decimal(s["profit"]) == Decimal("649.50") and Decimal(s["margin"]) == Decimal("65.0")
    assert Decimal(s["to_pay"]) == Decimal("900.00") and [c["id"] for c in s["upcoming"]] == [bill["id"]]

    # Paying the bill moves it into money out.
    marked = (await api.post(f"/costs/{bill['id']}/paid", json={}, headers=h)).json()
    assert marked["status"] == "paid" and marked["paid_date"] == TODAY.isoformat()
    s = (await api.get("/costs/summary", headers=h)).json()
    assert Decimal(s["money_out"]) == Decimal("1250.50") and Decimal(s["profit"]) == Decimal("-250.50") and s["upcoming"] == []
    # And back, if it was a mistake.
    assert (await api.post(f"/costs/{bill['id']}/unpaid", headers=h)).json()["status"] == "due"

    listed = (await api.get("/costs", headers=h)).json()
    assert Decimal(listed["total_paid"]) == Decimal("350.50") and Decimal(listed["total_due"]) == Decimal("900.00")
    assert (await api.get("/costs", params={"category": "stock"}, headers=h)).json()["items"][0]["description"] == "Gas bottles"
    assert "utilities" in (await api.get("/costs/categories", headers=h)).json()

    # An empty month: no margin rather than a division by zero.
    empty = (await api.get("/costs/summary", params={"month": "2020-01"}, headers=h)).json()
    assert Decimal(empty["money_in"]) == 0 and empty["margin"] is None
    assert (await api.get("/costs/summary", params={"month": "soon"}, headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_costs_are_for_admins_and_managers_and_stay_in_their_company(api):
    owner = await new_company(api, "Private Spend")
    h = owner["headers"]
    cost = (await api.post("/costs", json={"description": "Salaries", "category": "salaries", "amount": "25000", "due_date": TODAY.isoformat()}, headers=h)).json()

    email = f"{uuid.uuid4().hex[:10]}@example.com"
    await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": "Sam", "role": "staff"}, headers=h)
    await mark_verified(email)
    staff = {"Authorization": f"Bearer {(await api.post('/auth/login', json={'email': email, 'password': 'Correct-Horse-9'})).json()['access_token']}"}
    assert (await api.get("/costs", headers=staff)).status_code == 403
    assert (await api.get("/costs/summary", headers=staff)).status_code == 403
    assert (await api.post("/costs", json={"description": "x", "category": "other", "amount": "1", "due_date": TODAY.isoformat()}, headers=staff)).status_code == 403

    other = await new_company(api, "Someone Else")
    assert (await api.get(f"/costs/{cost['id']}", headers=other["headers"])).status_code == 404
    assert (await api.get("/costs", headers=other["headers"])).json()["items"] == []

    # Nothing negative or zero, and a category is required.
    bad = await api.post("/costs", json={"description": "Refund", "category": "other", "amount": "-5", "due_date": TODAY.isoformat()}, headers=h)
    assert bad.status_code == 422
    assert (await api.post("/costs", json={"description": "x", "category": "  ", "amount": "5", "due_date": TODAY.isoformat()}, headers=h)).status_code == 422


@pytest.mark.asyncio
async def test_a_recurring_bill_appears_a_week_ahead_once_and_is_never_paid_by_itself(api):
    owner = await new_company(api, "Rent Payers")
    h = owner["headers"]
    start = TODAY + timedelta(days=3)
    rent = await api.post("/recurring-costs", json={"description": "Shop rent", "category": "rent", "amount": "8000", "frequency": "monthly", "start_date": start.isoformat()}, headers=h)
    assert rent.status_code == 201, rent.text
    rent = rent.json()
    bills = (await api.get("/costs", headers=h)).json()["items"]
    # Due in 3 days: inside the week's lead, so the first bill is ready, unpaid.
    assert [(b["description"], b["status"], b["due_date"]) for b in bills] == [("Shop rent", "due", start.isoformat())]
    assert rent["next_run_date"] > start.isoformat()

    cid = await company_id(api, h)
    async with AsyncSessionLocal() as db:
        set_tenant(db, cid)
        # The daily run made nothing new: that cycle exists already.
        assert await RecurringCostService(db).make_all_due(TODAY) == 0
        # A month on, the next cycle appears, also unpaid.
        assert await RecurringCostService(db).make_all_due(TODAY + timedelta(days=31)) == 1
        await db.commit()
    bills = (await api.get("/costs", headers=h)).json()["items"]
    assert len(bills) == 2 and {b["status"] for b in bills} == {"due"}

    # Pausing stops it; resuming skips the missed cycles.
    assert (await api.post(f"/recurring-costs/{rent['id']}/pause", headers=h)).json()["active"] is False
    async with AsyncSessionLocal() as db:
        set_tenant(db, cid)
        assert await RecurringCostService(db).make_all_due(TODAY + timedelta(days=120)) == 0
    # Deleting the schedule keeps its bills.
    assert (await api.delete(f"/recurring-costs/{rent['id']}", headers=h)).status_code == 204
    assert len((await api.get("/costs", headers=h)).json()["items"]) == 2


@pytest.mark.asyncio
async def test_bills_due_soon_remind_admins_once(api):
    owner = await new_company(api, "Reminded Co")
    h = owner["headers"]
    soon = (await api.post("/costs", json={"description": "Insurance", "category": "other", "amount": "1200", "due_date": (TODAY + timedelta(days=2)).isoformat()}, headers=h)).json()
    await api.post("/costs", json={"description": "Later", "category": "other", "amount": "50", "due_date": (TODAY + timedelta(days=20)).isoformat()}, headers=h)
    cid = await company_id(api, h)
    async with AsyncSessionLocal() as db:
        set_tenant(db, cid)
        assert await CostService(db).remind_due(TODAY) == 1
        assert await CostService(db).remind_due(TODAY) == 0  # once
        notes = (await db.scalars(select(Notification).where(Notification.kind == "bill_due"))).all()
        assert len(notes) == 1 and notes[0].params["description"] == "Insurance" and soon["id"] in notes[0].key


@pytest.mark.asyncio
async def test_a_sent_purchase_order_is_recorded_as_a_cost_once(api):
    owner = await new_company(api, "PO Buyers")
    h = owner["headers"]
    supplier = (await api.post("/suppliers", json={"name": "Fresh Farms"}, headers=h)).json()
    po = (await api.post("/purchase-orders", json={"supplier_id": supplier["id"], "issue_date": TODAY.isoformat(), "items": ITEM}, headers=h)).json()
    draft = await api.post(f"/costs/from-purchase-order/{po['id']}", json={}, headers=h)
    assert draft.status_code == 409 and draft.json()["error_code"] == "COST_PO_NOT_SENT"
    await api.post(f"/purchase-orders/{po['id']}/send", params={"notify": "false"}, headers=h)
    assert (await api.get(f"/costs/from-purchase-order/{po['id']}", headers=h)).json() is None

    cost = await api.post(f"/costs/from-purchase-order/{po['id']}", json={"paid": True}, headers=h)
    assert cost.status_code == 201, cost.text
    cost = cost.json()
    assert Decimal(cost["amount"]) == Decimal(po["total"]) and cost["category"] == "stock" and cost["status"] == "paid"
    assert cost["supplier_id"] == supplier["id"] and po["po_number"] in cost["description"]
    assert (await api.get(f"/costs/from-purchase-order/{po['id']}", headers=h)).json()["id"] == cost["id"]
    again = await api.post(f"/costs/from-purchase-order/{po['id']}", json={}, headers=h)
    assert again.status_code == 409 and again.json()["error_code"] == "COST_PO_ALREADY"


@pytest.mark.asyncio
async def test_a_receipt_photo_or_pdf_is_kept_with_the_cost(api):
    owner = await new_company(api, "Receipt Keepers")
    h = owner["headers"]
    cost = (await api.post("/costs", json={"description": "Fuel", "category": "transport", "amount": "640", "due_date": TODAY.isoformat(), "paid": True}, headers=h)).json()
    pdf = b"%PDF-1.4 receipt"
    added = await api.post(f"/costs/{cost['id']}/receipt", files={"file": ("slip.pdf", pdf, "application/pdf")}, headers=h)
    assert added.status_code == 200 and added.json()["receipt_name"] == "slip.pdf"
    got = await api.get(f"/costs/{cost['id']}/receipt", headers=h)
    assert got.content == pdf and "attachment" in got.headers["content-disposition"]
    bad = await api.post(f"/costs/{cost['id']}/receipt", files={"file": ("page.html", b"<script>", "text/html")}, headers=h)
    assert bad.status_code == 422 and bad.json()["error_code"] == "RECEIPT_BAD_TYPE"
    assert (await api.delete(f"/costs/{cost['id']}/receipt", headers=h)).json()["receipt_name"] is None


@pytest.mark.asyncio
async def test_the_money_dashboard_shows_twelve_months_and_where_money_went(api):
    owner = await new_company(api, "Dashboard Bakery")
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Café Lindiwe"}, headers=h)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": TODAY.isoformat(), "items": ITEM}, headers=h)).json()
    await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/invoices/{invoice['id']}/payments", json={"amount": "1000.00", "method": "eft"}, headers=h)
    for desc, cat, amount in (("Flour", "stock", "300"), ("Butter", "stock", "200"), ("Rent", "rent", "400")):
        await api.post("/costs", json={"description": desc, "category": cat, "amount": amount, "due_date": TODAY.isoformat(), "paid": True}, headers=h)
    await api.post("/costs", json={"description": "Electricity", "category": "utilities", "amount": "90", "due_date": (TODAY - timedelta(days=1)).isoformat()}, headers=h)

    o = await api.get("/costs/overview", headers=h)
    assert o.status_code == 200, o.text
    o = o.json()
    assert len(o["months"]) == 12 and o["months"][-1]["month"] == TODAY.replace(day=1).isoformat()
    last = o["months"][-1]
    assert Decimal(last["money_in"]) == 1000 and Decimal(last["money_out"]) == 900 and Decimal(last["profit"]) == 100
    assert Decimal(o["profit"]) == 100 and Decimal(o["margin"]) == Decimal("10.0")
    assert [(c["category"], Decimal(c["total"])) for c in o["by_category"]] == [("stock", 500), ("rent", 400)]
    assert Decimal(o["to_come_in"]) == Decimal("150.00")  # the invoice's unpaid balance
    assert Decimal(o["to_pay"]) == 90 and Decimal(o["overdue_out"]) == 90

    # Hustle keeps the Costs page but not the full dashboard.
    small = await new_company(api, "Small Hustle", plan="hustle")
    assert (await api.get("/costs/overview", headers=small["headers"])).status_code == 402
    assert (await api.get("/costs/summary", headers=small["headers"])).status_code == 200


@pytest.mark.asyncio
async def test_review_fixes_old_lease_paid_date_overdue_title_and_end_date(api):
    owner = await new_company(api, "Review Fixes")
    h = owner["headers"]
    # A lease that began long ago bills only its latest cycle, not a pile.
    lease = (await api.post("/recurring-costs", json={"description": "Shop rent", "category": "rent", "amount": "8000", "frequency": "monthly", "start_date": "2025-01-01"}, headers=h)).json()
    bills = (await api.get("/costs", params={"status": "due"}, headers=h)).json()["items"]
    assert len(bills) <= 2, [b["due_date"] for b in bills]  # this month's, and next month's if it's within the week
    assert bills and all(b["due_date"] >= TODAY.replace(day=1).isoformat() for b in bills)

    # An end date before the next bill is refused.
    bad = await api.patch(f"/recurring-costs/{lease['id']}", json={"end_date": "2025-06-01"}, headers=h)
    assert bad.status_code == 422

    # A paid cost's paid date can be corrected, moving it to that month.
    cost = (await api.post("/costs", json={"description": "Gas", "category": "stock", "amount": "100", "due_date": TODAY.isoformat(), "paid": True}, headers=h)).json()
    moved = (await api.patch(f"/costs/{cost['id']}", json={"paid_date": "2026-01-15", "due_date": "2026-01-15"}, headers=h)).json()
    assert moved["paid_date"] == "2026-01-15"
    assert Decimal((await api.get("/costs/summary", params={"month": "2026-01"}, headers=h)).json()["money_out"]) == 100

    # An overdue bill's email subject reads as overdue.
    await api.post("/costs", json={"description": "Water", "category": "utilities", "amount": "50", "due_date": (TODAY - timedelta(days=3)).isoformat()}, headers=h)
    cid = await company_id(api, h)
    async with AsyncSessionLocal() as db:
        set_tenant(db, cid)
        await CostService(db).remind_due(TODAY)
        titles = (await db.scalars(select(Notification.title).where(Notification.kind == "bill_due"))).all()
        assert any(t.startswith("Overdue bill: Water") for t in titles) and not any("due overdue" in t for t in titles)
