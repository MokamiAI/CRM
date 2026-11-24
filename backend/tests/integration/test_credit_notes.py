"""Credit notes: reduce an invoice after it has gone out, even after a part
payment. The invoice keeps its total (it's the customer's tax invoice);
what's owed, its status, the quote's final amount, the statement and the
reports all follow the credit note. A credit note issued by mistake is
voided and its amount goes back on the invoice."""
from decimal import Decimal

import pytest

from .conftest import new_company

FOOD = {"description": "Wedding buffet, 120 guests", "quantity": "120", "unit_price": "185.00", "tax_rate": "15"}
HIRE = {"description": "Venue hire (VAT exempt)", "quantity": "1", "unit_price": "3333.33", "tax_rate": "0"}


async def sent_invoice(api, name, items=None):
    owner = await new_company(api, name)
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Ops Client", "email": "accounts@client.example.com"}, headers=h)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "due_date": "2099-12-01",
                                                 "items": items or [FOOD]}, headers=h)).json()
    await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=h)
    return h, customer, invoice


async def pay(api, h, invoice_id, amount):
    res = await api.post(f"/invoices/{invoice_id}/payments", json={"amount": amount, "method": "eft"}, params={"notify": "false"}, headers=h)
    assert res.status_code == 201, res.text


@pytest.mark.asyncio
async def test_credit_after_a_part_payment_lowers_what_is_owed(api):
    h, customer, invoice = await sent_invoice(api, "Credit After Payment")
    total = Decimal(invoice["total"])  # 120 x 185 + 15% = 25 530.00
    await pay(api, h, invoice["id"], "10000.00")

    res = await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "2000.00", "reason": "Discount agreed with client"}, headers=h)
    assert res.status_code == 201, res.text
    note = res.json()
    assert note["credit_note_number"] == "CN-0001" and note["invoice_number"] == invoice["invoice_number"]
    assert Decimal(note["total"]) == Decimal("2000.00")  # exactly what was typed
    assert Decimal(note["subtotal"]) + Decimal(note["tax_total"]) == Decimal("2000.00")
    assert Decimal(note["tax_total"]) == (Decimal("2000.00") * Decimal(invoice["tax_total"]) / total).quantize(Decimal("0.01"))

    after = (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()
    assert Decimal(after["total"]) == total  # the tax invoice itself is unchanged
    assert Decimal(after["amount_credited"]) == Decimal("2000.00")
    assert Decimal(after["amount_due"]) == total - Decimal("2000.00") - Decimal("10000.00")
    assert after["status"] == "partially_paid"

    # Paying what's now owed settles it; a cent more is refused.
    over = await api.post(f"/invoices/{invoice['id']}/payments", json={"amount": str(Decimal(after["amount_due"]) + Decimal("0.01")), "method": "eft"}, headers=h)
    assert over.status_code == 409
    await pay(api, h, invoice["id"], after["amount_due"])
    assert (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()["status"] == "paid"

    # Second number, listed on the invoice, printable, and on the timeline.
    listed = (await api.get(f"/invoices/{invoice['id']}/credit-notes", headers=h)).json()
    assert [n["credit_note_number"] for n in listed] == ["CN-0001"]
    doc = await api.get(f"/credit-notes/{note['id']}/document", headers=h)
    assert doc.status_code == 200 and "Credit note" in doc.text and invoice["invoice_number"] in doc.text and "Discount agreed" in doc.text
    inv_doc = (await api.get(f"/invoices/{invoice['id']}/document", headers=h)).text
    assert "Credit notes" in inv_doc


@pytest.mark.asyncio
async def test_crediting_below_what_was_paid_shows_a_refund(api):
    h, customer, invoice = await sent_invoice(api, "Credit Refund")
    total = Decimal(invoice["total"])
    await pay(api, h, invoice["id"], str(total - Decimal("1000.00")))
    await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "3000.00", "reason": "Two staff short on the day"}, headers=h)
    after = (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()
    assert after["status"] == "paid" and Decimal(after["amount_due"]) == 0 and Decimal(after["refund_due"]) == Decimal("2000.00")


@pytest.mark.asyncio
async def test_rest_credits_exactly_what_is_left_per_vat_rate_and_no_more(api):
    h, customer, invoice = await sent_invoice(api, "Credit Rest", items=[FOOD, HIRE])
    first = (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "1234.56", "reason": "Part refund"}, headers=h)).json()
    assert {Decimal(i["tax_rate"]) for i in first["items"]} == {Decimal("0"), Decimal("15")}  # one line per VAT rate
    rest = (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "rest", "reason": "Event cancelled"}, headers=h)).json()
    assert Decimal(first["total"]) + Decimal(rest["total"]) == Decimal(invoice["total"])  # to the cent
    assert Decimal(first["tax_total"]) + Decimal(rest["tax_total"]) == Decimal(invoice["tax_total"])
    after = (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()
    assert after["status"] == "paid" and Decimal(after["amount_due"]) == 0  # nothing left to pay

    more = await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "1", "reason": "again"}, headers=h)
    assert more.status_code == 409 and more.json()["error_code"] == "INVOICE_FULLY_CREDITED"


@pytest.mark.asyncio
async def test_too_large_draft_void_and_roles_are_refused(api):
    h, customer, invoice = await sent_invoice(api, "Credit Limits")
    too_big = await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": str(Decimal(invoice["total"]) + 1), "reason": "x" * 5}, headers=h)
    assert too_big.status_code == 409 and too_big.json()["error_code"] == "CREDIT_TOO_LARGE"
    assert (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "10", "reason": " "}, headers=h)).status_code == 422

    draft = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "items": [FOOD]}, headers=h)).json()
    res = await api.post(f"/invoices/{draft['id']}/credit-notes", json={"kind": "amount", "value": "10", "reason": "Not sent"}, headers=h)
    assert res.status_code == 409 and res.json()["error_code"] == "INVOICE_NOT_CREDITABLE"

    # With a credit note on it, the invoice can't be voided or "corrected".
    await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "100", "reason": "Discount"}, headers=h)
    void = await api.post(f"/invoices/{invoice['id']}/void", headers=h)
    assert void.status_code == 409 and void.json()["error_code"] == "INVOICE_HAS_CREDIT_NOTES"
    assert (await api.post(f"/invoices/{invoice['id']}/correct", headers=h)).status_code == 409

    # Another company can't see or credit it.
    other = await new_company(api, "Credit Outsider")
    assert (await api.get(f"/invoices/{invoice['id']}/credit-notes", headers=other["headers"])).json() == []
    assert (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "1", "reason": "Sneaky"}, headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_voiding_a_credit_note_puts_the_amount_back(api):
    h, customer, invoice = await sent_invoice(api, "Credit Void")
    note = (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "rest", "reason": "Typed in error"}, headers=h)).json()
    assert (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()["status"] == "paid"
    voided = await api.post(f"/credit-notes/{note['id']}/void", headers=h)
    assert voided.status_code == 200 and voided.json()["status"] == "void"
    after = (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()
    assert after["status"] == "sent" and Decimal(after["amount_credited"]) == 0 and Decimal(after["amount_due"]) == Decimal(invoice["total"])
    assert (await api.post(f"/credit-notes/{note['id']}/void", headers=h)).status_code == 409
    # The void one stays on record, and the next number follows on.
    nxt = (await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "50", "reason": "Real discount"}, headers=h)).json()
    assert nxt["credit_note_number"] == "CN-0002"


@pytest.mark.asyncio
async def test_email_goes_only_when_asked(api):
    h, customer, invoice = await sent_invoice(api, "Credit Email")
    api.queued.clear()
    await api.post(f"/invoices/{invoice['id']}/credit-notes", json={"kind": "amount", "value": "10", "reason": "Quiet"}, headers=h)
    assert not [q for q in api.queued if "credit_note" in q[0]]
    note = (await api.post(f"/invoices/{invoice['id']}/credit-notes", params={"notify": "true"}, json={"kind": "amount", "value": "10", "reason": "Loud"}, headers=h)).json()
    assert [q for q in api.queued if "credit_note" in q[0]] == [("app.tasks.email_tasks.send_credit_note_email_task", (note["id"],))]

    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system
    from app.services.notification_service import NotificationService

    async with AsyncSessionLocal() as db:
        set_system(db)
        import uuid

        email = await NotificationService(db).compose_credit_note_sent(uuid.UUID(note["id"]))
    assert email.to == "accounts@client.example.com" and note["credit_note_number"] in email.subject and "Loud" in email.text


@pytest.mark.asyncio
async def test_quote_shows_its_final_amount_and_the_statement_the_credit(api):
    owner = await new_company(api, "Credit Quote")
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Mokoena Wedding"}, headers=h)).json()
    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "items": [FOOD]}, headers=h)).json()
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/quotes/{quote['id']}/accept", headers=h)
    deposit = (await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "percent", "value": "50", "replace_draft": True}, headers=h)).json()
    await api.post(f"/invoices/{deposit['id']}/send", params={"notify": "false"}, headers=h)
    await pay(api, h, deposit["id"], "5000.00")
    await api.post(f"/invoices/{deposit['id']}/credit-notes", json={"kind": "amount", "value": "1530.00", "reason": "Ten fewer guests"}, headers=h)

    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    assert Decimal(billing["total"]) == Decimal(quote["total"])  # what was agreed stays
    assert Decimal(billing["credited"]) == Decimal("1530.00")
    assert Decimal(billing["final_total"]) == Decimal(quote["total"]) - Decimal("1530.00")
    # A credit isn't billed again: the balance is still the other half.
    assert Decimal(billing["remaining"]) == Decimal(quote["total"]) - Decimal(deposit["total"])

    statement = (await api.get(f"/customers/{customer['id']}/statement", params={"start": "2026-01-01", "end": "2099-01-01"}, headers=h)).json()
    assert [line["kind"] for line in statement["lines"]] == ["invoice", "credit_note", "payment"]
    assert Decimal(str(statement["credited"])) == Decimal("1530.00")
    assert Decimal(str(statement["closing_balance"])) == Decimal(deposit["total"]) - Decimal("1530.00") - Decimal("5000.00")

    timeline = (await api.get(f"/customers/{customer['id']}/timeline", headers=h)).json()
    assert any(item["kind"] == "credit_note" for item in timeline)
