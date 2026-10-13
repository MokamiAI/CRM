"""Accepting a quote makes exactly one draft invoice, copied from the quote,
seen only by its own company, and nothing is emailed to the customer."""
import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.models.invoice import Invoice
from app.services.quote_service import QuoteService

from .conftest import new_company

ITEMS = [
    {"description": "Catering per guest", "quantity": "120", "unit_price": "280.00", "tax_rate": "15"},
    {"description": "Delivery and setup", "quantity": "1", "unit_price": "750.00", "tax_rate": "15"},
]


async def _sent_quote(api, owner) -> tuple[dict, dict]:
    headers = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Naledi Events", "email": "naledi@example.com"}, headers=headers)).json()
    res = await api.post(
        "/quotes",
        json={
            "customer_id": customer["id"],
            "issue_date": "2026-10-14",
            "reference": "Wedding, 120 guests",
            "po_number": "PO-77",
            "notes": "Thank you for choosing us.",
            "items": ITEMS,
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    quote = res.json()
    res = await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=headers)
    assert res.status_code == 200, res.text
    return customer, quote


@pytest.mark.asyncio
async def test_accepting_a_quote_makes_one_draft_invoice(api):
    owner = await new_company(api, "Alpha Catering")
    customer, quote = await _sent_quote(api, owner)
    accept = f"/quotes/{quote['id']}/accept"
    queued_before = len(api.queued)

    # A double click: two accepts at the same moment.
    first, second = await asyncio.gather(api.post(accept, headers=owner["headers"]), api.post(accept, headers=owner["headers"]))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    invoice_id = first.json()["invoice_id"]
    assert invoice_id and second.json()["invoice_id"] == invoice_id
    assert first.json()["invoice_number"]

    # And again later: still the same draft.
    again = await api.post(accept, headers=owner["headers"])
    assert again.status_code == 200 and again.json()["invoice_id"] == invoice_id

    invoices = (await api.get("/invoices", params={"customer_id": customer["id"]}, headers=owner["headers"])).json()
    assert [i["id"] for i in invoices] == [invoice_id]
    invoice = invoices[0]
    assert invoice["status"] == "draft"
    assert invoice["quote_id"] == quote["id"]
    assert invoice["reference"] == "Wedding, 120 guests" and invoice["po_number"] == "PO-77"
    for field in ("subtotal", "tax_total", "total"):
        assert Decimal(invoice[field]) == Decimal(quote[field]), field
    assert Decimal(invoice["total"]) == Decimal("39502.50")  # (33 600 + 750) + 15% VAT
    assert [(i["description"], Decimal(i["line_total"])) for i in invoice["items"]] == [
        (i["description"], Decimal(i["line_total"])) for i in quote["items"]
    ]

    converted = (await api.get(f"/quotes/{quote['id']}", headers=owner["headers"])).json()
    assert converted["status"] == "converted"
    # Nothing was queued for sending: the draft waits for a person.
    assert api.queued[queued_before:] == []


@pytest.mark.asyncio
async def test_only_a_sent_quote_can_be_accepted(api):
    owner = await new_company(api, "Beta Builders")
    customer = (await api.post("/customers", json={"name": "Mr Dlamini"}, headers=owner["headers"])).json()
    draft = (
        await api.post(
            "/quotes",
            json={"customer_id": customer["id"], "issue_date": "2026-10-14", "items": ITEMS[:1]},
            headers=owner["headers"],
        )
    ).json()
    res = await api.post(f"/quotes/{draft['id']}/accept", headers=owner["headers"])
    assert res.status_code == 409
    invoices = (await api.get("/invoices", headers=owner["headers"])).json()
    assert invoices == []


@pytest.mark.asyncio
async def test_another_company_cannot_accept_or_see_it(api):
    owner = await new_company(api, "Gamma Cleaning")
    other = await new_company(api, "Delta Decor")
    _, quote = await _sent_quote(api, owner)

    res = await api.post(f"/quotes/{quote['id']}/accept", headers=other["headers"])
    assert res.status_code == 404

    invoice_id = (await api.post(f"/quotes/{quote['id']}/accept", headers=owner["headers"])).json()["invoice_id"]
    assert (await api.get(f"/invoices/{invoice_id}", headers=other["headers"])).status_code == 404
    assert (await api.get("/invoices", headers=other["headers"])).json() == []


@pytest.mark.asyncio
async def test_two_accepts_at_once_wait_for_each_other(api):
    """Two sessions accept the same quote truly at once: the second waits for
    the first to finish, then gets the same draft back, not a second one."""
    owner = await new_company(api, "Zeta Events")
    _, quote = await _sent_quote(api, owner)
    quote_id = uuid.UUID(quote["id"])

    async with AsyncSessionLocal() as first, AsyncSessionLocal() as second:
        set_tenant(first, owner["company_id"])
        set_tenant(second, owner["company_id"])
        _, invoice = await QuoteService(first).accept(quote_id, accepted_by=owner["user_id"])
        racing = asyncio.create_task(QuoteService(second).accept(quote_id, accepted_by=owner["user_id"]))
        await asyncio.sleep(0.5)
        assert not racing.done(), "the second accept should wait for the first to commit"
        await first.commit()
        _, same = await racing
        await second.commit()
        assert same is not None and same.id == invoice.id

    invoices = (await api.get("/invoices", headers=owner["headers"])).json()
    assert [i["id"] for i in invoices] == [str(invoice.id)]


@pytest.mark.asyncio
async def test_database_allows_one_invoice_per_quote(api):
    owner = await new_company(api, "Eta Electrical")
    _, quote = await _sent_quote(api, owner)
    invoice_id = (await api.post(f"/quotes/{quote['id']}/accept", headers=owner["headers"])).json()["invoice_id"]
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        original = await db.get(Invoice, uuid.UUID(invoice_id))
        db.add(
            Invoice(
                company_id=original.company_id,
                invoice_number=original.invoice_number + "-B",
                customer_id=original.customer_id,
                quote_id=original.quote_id,
                issue_date=original.issue_date,
                due_date=original.due_date,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
