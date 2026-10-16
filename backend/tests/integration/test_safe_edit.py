"""Edit on documents that already went out: a sent quote goes back to
draft; a sent, unpaid invoice is voided and copied to a new draft. Answers
and payments are never undone."""
import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.services.invoice_service import InvoiceService

from .conftest import mark_verified, new_company

ITEMS = [
    {"description": "Platter (serves 10)", "quantity": "2", "unit_price": "650", "tax_rate": "15"},
    {"description": "Delivery", "quantity": "1", "unit_price": "250", "tax_rate": "15"},
]
TODAY = date.today().isoformat()


async def _customer(api, h):
    return (await api.post("/customers", json={"name": f"Client {uuid.uuid4().hex[:5]}"}, headers=h)).json()["id"]


@pytest.mark.asyncio
async def test_sent_quote_goes_back_to_draft_to_edit(api):
    h = (await new_company(api, "Chi Caterers"))["headers"]
    quote = (await api.post("/quotes", json={"customer_id": await _customer(api, h), "issue_date": TODAY, "items": ITEMS}, headers=h)).json()
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    assert (await api.patch(f"/quotes/{quote['id']}", json={"notes": "x"}, headers=h)).status_code == 409

    revised = await api.post(f"/quotes/{quote['id']}/revise", headers=h)
    assert revised.status_code == 200 and revised.json()["status"] == "draft"
    edited = (await api.patch(f"/quotes/{quote['id']}", json={"notes": "Now with dessert", "items": ITEMS[:1]}, headers=h)).json()
    assert edited["notes"] == "Now with dessert" and Decimal(edited["total"]) == Decimal("1495.00")
    assert edited["quote_number"] == quote["quote_number"]

    # An answer is never undone.
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/quotes/{quote['id']}/reject", headers=h)
    assert (await api.post(f"/quotes/{quote['id']}/revise", headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_sent_invoice_is_voided_and_copied_to_a_draft(api):
    owner = await new_company(api, "Psi Plumbing")
    h = owner["headers"]
    inv = (await api.post("/invoices", json={"customer_id": await _customer(api, h), "issue_date": TODAY, "reference": "Job 12", "po_number": "PO-9", "notes": "Thanks", "items": ITEMS}, headers=h)).json()
    await api.post(f"/invoices/{inv['id']}/send", params={"notify": "false"}, headers=h)

    res = await api.post(f"/invoices/{inv['id']}/correct", headers=h)
    assert res.status_code == 201, res.text
    copy = res.json()
    assert copy["status"] == "draft" and copy["invoice_number"] != inv["invoice_number"]
    assert (copy["customer_id"], copy["reference"], copy["po_number"], copy["notes"]) == (inv["customer_id"], "Job 12", "PO-9", "Thanks")
    assert [i["description"] for i in copy["items"]] == [i["description"] for i in ITEMS] and copy["total"] == inv["total"]
    assert (await api.get(f"/invoices/{inv['id']}", headers=h)).json()["status"] == "void"
    assert (await api.post(f"/invoices/{inv['id']}/correct", headers=h)).status_code == 409  # already void
    assert (await api.patch(f"/invoices/{copy['id']}", json={"notes": "Fixed"}, headers=h)).json()["notes"] == "Fixed"


@pytest.mark.asyncio
async def test_paid_invoices_and_staff_cannot_correct(api):
    owner = await new_company(api, "Omega Electrical")
    h = owner["headers"]
    inv = (await api.post("/invoices", json={"customer_id": await _customer(api, h), "issue_date": TODAY, "items": ITEMS}, headers=h)).json()
    await api.post(f"/invoices/{inv['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/invoices/{inv['id']}/payments", json={"amount": "100.00", "method": "eft"}, headers=h)
    res = await api.post(f"/invoices/{inv['id']}/correct", headers=h)
    assert res.status_code == 409 and res.json()["error_code"] == "INVOICE_NOT_CORRECTABLE"

    email = f"{uuid.uuid4().hex[:10]}@example.com"
    await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": "Sam Staff", "role": "staff"}, headers=h)
    await mark_verified(email)
    staff = {"Authorization": f"Bearer {(await api.post('/auth/login', json={'email': email, 'password': 'Correct-Horse-9'})).json()['access_token']}"}
    other = (await api.post("/invoices", json={"customer_id": await _customer(api, h), "issue_date": TODAY, "items": ITEMS}, headers=h)).json()
    await api.post(f"/invoices/{other['id']}/send", params={"notify": "false"}, headers=h)
    assert (await api.post(f"/invoices/{other['id']}/correct", headers=staff)).status_code == 403

    stranger = (await new_company(api, "Alpha Two"))["headers"]
    assert (await api.post(f"/invoices/{other['id']}/correct", headers=stranger)).status_code == 404


@pytest.mark.asyncio
async def test_two_corrections_at_once_make_one_copy(api):
    owner = await new_company(api, "Beta Two")
    h = owner["headers"]
    inv = (await api.post("/invoices", json={"customer_id": await _customer(api, h), "issue_date": TODAY, "items": ITEMS}, headers=h)).json()
    await api.post(f"/invoices/{inv['id']}/send", params={"notify": "false"}, headers=h)

    async def run():
        async with AsyncSessionLocal() as db:
            set_tenant(db, owner["company_id"])
            try:
                await InvoiceService(db).correct(uuid.UUID(inv["id"]), owner["user_id"])
                await asyncio.sleep(0.3)
                await db.commit()
                return 1
            except Exception:
                await db.rollback()
                return 0

    assert sorted(await asyncio.gather(run(), run())) == [0, 1]
    drafts = (await api.get("/invoices", params={"status": "draft"}, headers=h)).json()
    assert len(drafts) == 1
