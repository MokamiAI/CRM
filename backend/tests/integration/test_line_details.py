"""A line has an item and, under it, an optional description: kept on the
quote, carried to the invoice it becomes, and printed on both."""
import pytest

from .conftest import new_company

LAPTOPS = {"description": "DELL PRO 15 ESSENTIAL PV15250", "details": "Intel Core i5, 16 GB RAM, 512 GB SSD\nThree-year on-site warranty",
           "quantity": "16", "unit_price": "14420.00", "tax_rate": "15"}
DELIVERY = {"description": "Delivery to Kokstad campus", "quantity": "1", "unit_price": "950.00", "tax_rate": "15"}


@pytest.mark.asyncio
async def test_item_and_description_on_the_quote_the_invoice_and_both_documents(api):
    owner = await new_company(api, "Line Details Co")
    headers = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Esayidi TVET College", "email": "quotes@example.com"}, headers=headers)).json()
    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": "2026-10-26", "items": [LAPTOPS, DELIVERY]}, headers=headers)).json()
    assert [(i["description"], i["details"]) for i in quote["items"]] == [(LAPTOPS["description"], LAPTOPS["details"]), (DELIVERY["description"], None)]

    page = (await api.get(f"/quotes/{quote['id']}/document", headers=headers)).text
    assert "DELL PRO 15 ESSENTIAL PV15250" in page and "Three-year on-site warranty" in page

    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=headers)
    accepted = await api.post(f"/quotes/{quote['id']}/accept", headers=headers)
    assert accepted.status_code in (200, 201), accepted.text
    invoices = (await api.get("/invoices", params={"customer_id": customer["id"]}, headers=headers)).json()
    invoice = (await api.get(f"/invoices/{invoices[0]['id']}", headers=headers)).json()
    assert invoice["items"][0]["details"] == LAPTOPS["details"] and invoice["items"][1]["details"] is None
    page = (await api.get(f"/invoices/{invoice['id']}/document", headers=headers)).text
    assert "Intel Core i5, 16 GB RAM, 512 GB SSD" in page


@pytest.mark.asyncio
async def test_a_blank_description_is_stored_as_none(api):
    owner = await new_company(api, "Blank Details Co")
    customer = (await api.post("/customers", json={"name": "Someone"}, headers=owner["headers"])).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-10-26",
               "items": [{**DELIVERY, "details": "   "}]}, headers=owner["headers"])).json()
    assert invoice["items"][0]["details"] is None
