"""An accepted quote invoiced in parts: a deposit, a stage, then the balance.
The parts add up to the quote to the cent, VAT per rate included, and the
draft made on acceptance can be replaced by the parts."""
from decimal import Decimal

import pytest

from .conftest import new_company

FOOD = {"description": "Wedding buffet, 120 guests", "quantity": "120", "unit_price": "185.00", "tax_rate": "15"}
HIRE = {"description": "Venue hire (VAT exempt)", "quantity": "1", "unit_price": "3333.33", "tax_rate": "0"}


async def accepted_quote(api, name):
    owner = await new_company(api, name)
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Mokoena Wedding"}, headers=h)).json()
    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "title": "Mokoena wedding, 12 Dec",
                                             "items": [FOOD, HIRE]}, headers=h)).json()
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    accepted = (await api.post(f"/quotes/{quote['id']}/accept", headers=h)).json()
    return h, quote, accepted


@pytest.mark.asyncio
async def test_deposit_stage_and_balance_add_up_to_the_quote(api):
    h, quote, accepted = await accepted_quote(api, "Staged Catering")
    total = Decimal(quote["total"])
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    # Acceptance made one draft for everything: offered for replacing.
    assert billing["draft_to_replace"]["id"] == accepted["invoice_id"] and Decimal(billing["remaining"]) == 0

    # Without replacing it there's nothing left to invoice.
    refused = await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "percent", "value": "50"}, headers=h)
    assert refused.status_code == 409 and refused.json()["error_code"] == "QUOTE_FULLY_INVOICED"

    deposit = await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "percent", "value": "50", "label": "Deposit", "replace_draft": True}, headers=h)
    assert deposit.status_code == 201, deposit.text
    deposit = deposit.json()
    assert deposit["items"][0]["description"].startswith("Deposit: 50% of quote")
    assert {Decimal(i["tax_rate"]) for i in deposit["items"]} == {Decimal("0"), Decimal("15")}  # one line per VAT rate
    assert (await api.get(f"/invoices/{accepted['invoice_id']}", headers=h)).status_code == 404  # the whole draft is gone

    stage = (await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "amount", "value": "5000"}, headers=h)).json()
    assert abs(Decimal(stage["total"]) - Decimal("5000")) <= Decimal("0.02")
    assert stage["items"][0]["description"].startswith("Progress payment:")

    too_much = await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "amount", "value": str(total)}, headers=h)
    assert too_much.status_code == 409

    balance = (await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "balance"}, headers=h)).json()
    parts = Decimal(deposit["total"]) + Decimal(stage["total"]) + Decimal(balance["total"])
    assert parts == total  # to the cent
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    assert Decimal(billing["remaining"]) == 0 and len(billing["invoices"]) == 3 and billing["draft_to_replace"] is None
    assert (await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "balance"}, headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_a_voided_part_frees_its_share_and_a_draft_quote_cant_be_invoiced(api):
    h, quote, accepted = await accepted_quote(api, "Staged Builders")
    deposit = (await api.post(f"/invoices/from-quote/{quote['id']}/part", json={"kind": "percent", "value": "30", "replace_draft": True}, headers=h)).json()
    await api.post(f"/invoices/{deposit['id']}/void", headers=h)
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    assert Decimal(billing["remaining"]) == Decimal(quote["total"])

    owner = await new_company(api, "Draft Quote Co")
    customer = (await api.post("/customers", json={"name": "Someone"}, headers=owner["headers"])).json()
    draft = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "items": [FOOD]}, headers=owner["headers"])).json()
    res = await api.post(f"/invoices/from-quote/{draft['id']}/part", json={"kind": "percent", "value": "50"}, headers=owner["headers"])
    assert res.status_code == 409 and res.json()["error_code"] == "QUOTE_NOT_ACCEPTED"
    assert (await api.post(f"/invoices/from-quote/{draft['id']}/part", json={"kind": "percent"}, headers=owner["headers"])).status_code == 422


# ---------- Found in code review: each reproduced, then fixed ----------

async def _with_lines(api, name, items, discount=None):
    """An accepted quote. `discount` adds a negative line on its own VAT rate,
    the way YGT's own subscription quotes carry a discount."""
    owner = await new_company(api, name)
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Client"}, headers=h)).json()
    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": "2026-11-01", "items": items}, headers=h)).json()
    if discount is not None:
        import uuid as _uuid
        from app.core.database import AsyncSessionLocal
        from app.core.tenancy import set_tenant
        from app.models.quote import Quote, QuoteItem
        from app.services.pricing import build_line_items
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from types import SimpleNamespace
        async with AsyncSessionLocal() as db:
            set_tenant(db, owner["company_id"])
            row = await db.scalar(select(Quote).options(selectinload(Quote.items)).where(Quote.id == _uuid.UUID(quote["id"])))
            lines = [SimpleNamespace(product_id=None, description=i.description, details=None, quantity=i.quantity, unit_price=i.unit_price, tax_rate=i.tax_rate) for i in row.items]
            lines.append(SimpleNamespace(product_id=None, description="Discount", details=None, quantity=Decimal("1"), unit_price=Decimal(discount), tax_rate=Decimal("0")))
            new_items, row.subtotal, row.tax_total, row.total = build_line_items(QuoteItem, lines)
            row.items.clear()
            row.items.extend(new_items)
            await db.commit()
        quote = (await api.get(f"/quotes/{quote['id']}", headers=h)).json()
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    accepted = (await api.post(f"/quotes/{quote['id']}/accept", headers=h)).json()
    return h, quote, accepted


def _part(api, h, quote, **body):
    return api.post(f"/invoices/from-quote/{quote['id']}/part", json=body, headers=h)


@pytest.mark.asyncio
async def test_a_discount_line_is_shared_by_the_parts_too(api):
    # R1000 at 15% plus a -R100 discount at 0%: R1050 in all.
    h, quote, _ = await _with_lines(api, "Discount Co", [{"description": "Work", "quantity": "1", "unit_price": "1000", "tax_rate": "15"}], discount="-100")
    assert Decimal(quote["total"]) == Decimal("1050.00")
    deposit = (await _part(api, h, quote, kind="percent", value="50", replace_draft=True)).json()
    assert Decimal(deposit["total"]) == Decimal("525.00")
    balance = (await _part(api, h, quote, kind="balance")).json()
    assert Decimal(balance["total"]) == Decimal("525.00")


@pytest.mark.asyncio
async def test_vat_rounded_per_line_still_adds_up_to_the_cent(api):
    # Two R10.10 lines at 15%: VAT 1.515 each, rounded per line to 1.52, so
    # the quote's VAT is 3.04 (not 3.03 on the summed R20.20).
    line = {"description": "Item", "quantity": "1", "unit_price": "10.10", "tax_rate": "15"}
    h, quote, _ = await _with_lines(api, "Rounding Co", [line, dict(line, description="Item 2")])
    assert Decimal(quote["tax_total"]) == Decimal("3.04")
    parts = [(await _part(api, h, quote, kind="percent", value="33.33", replace_draft=True)).json()]
    parts.append((await _part(api, h, quote, kind="percent", value="33.33")).json())
    parts.append((await _part(api, h, quote, kind="balance")).json())
    assert sum(Decimal(p["total"]) for p in parts) == Decimal(quote["total"])
    assert sum(Decimal(p["tax_total"]) for p in parts) == Decimal(quote["tax_total"])
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    assert Decimal(billing["remaining"]) == 0


@pytest.mark.asyncio
async def test_an_edited_draft_is_never_deleted(api):
    h, quote, accepted = await _with_lines(api, "Edited Draft Co", [FOOD])
    draft = (await api.get(f"/invoices/{accepted['invoice_id']}", headers=h)).json()
    items = [{k: i[k] for k in ("description", "quantity", "unit_price", "tax_rate")} for i in draft["items"]]
    items.append({"description": "Call-out fee", "quantity": "1", "unit_price": "500", "tax_rate": "15"})
    assert (await api.patch(f"/invoices/{draft['id']}", json={"items": items}, headers=h)).status_code == 200
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    assert billing["draft_to_replace"] is None and billing["draft_edited"]["id"] == draft["id"]
    refused = await _part(api, h, quote, kind="percent", value="50", replace_draft=True)
    assert refused.status_code == 409 and refused.json()["error_code"] == "QUOTE_DRAFT_EDITED"
    assert (await api.get(f"/invoices/{draft['id']}", headers=h)).status_code == 200  # still there


@pytest.mark.asyncio
async def test_a_percentage_bigger_than_whats_left_is_refused(api):
    h, quote, _ = await _with_lines(api, "Too Much Co", [FOOD])
    await _part(api, h, quote, kind="percent", value="50", replace_draft=True)
    refused = await _part(api, h, quote, kind="percent", value="60")
    assert refused.status_code == 409 and refused.json()["error_code"] == "QUOTE_PART_TOO_LARGE"


@pytest.mark.asyncio
async def test_an_edited_part_keeps_whats_left_and_the_balance_in_step(api):
    h, quote, _ = await _with_lines(api, "Edited Part Co", [FOOD])
    deposit = (await _part(api, h, quote, kind="percent", value="50", replace_draft=True)).json()
    # The deposit draft is changed to a round R10 000 incl. VAT.
    await api.patch(f"/invoices/{deposit['id']}", json={"items": [{"description": "Deposit", "quantity": "1", "unit_price": "8695.65", "tax_rate": "15"}]}, headers=h)
    edited = (await api.get(f"/invoices/{deposit['id']}", headers=h)).json()
    billing = (await api.get(f"/invoices/from-quote/{quote['id']}/billing", headers=h)).json()
    left = Decimal(quote["total"]) - Decimal(edited["total"])
    assert Decimal(billing["remaining"]) == left
    balance = (await _part(api, h, quote, kind="balance")).json()
    assert Decimal(balance["total"]) == left


@pytest.mark.asyncio
async def test_accepting_again_never_points_at_a_voided_invoice(api):
    h, quote, accepted = await _with_lines(api, "Void Point Co", [FOOD])
    await api.post(f"/invoices/{accepted['invoice_id']}/void", headers=h)
    deposit = (await _part(api, h, quote, kind="percent", value="30")).json()
    again = (await api.post(f"/quotes/{quote['id']}/accept", headers=h)).json()
    assert again["invoice_id"] == deposit["id"]
