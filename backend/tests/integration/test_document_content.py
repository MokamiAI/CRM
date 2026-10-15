"""Printed quotes and invoices carry the details on a proper tax invoice:
both parties, the contact person, delivery address, who prepared it, the
bank with its branch, and (on quotes) a title and description."""
from datetime import date

import pytest

from .conftest import new_company

ITEM = [{"description": "Freshdesk Omnichannel Pro - Annual", "quantity": "4", "unit_price": "14176.16", "tax_rate": "15"}]
TODAY = date.today().isoformat()


@pytest.mark.asyncio
async def test_documents_show_company_customer_and_contact_details(api):
    owner = await new_company(api, "Intermediate Data Systems")
    h = owner["headers"]
    await api.patch("/settings", json={"address": "4th Floor, 96 Rivonia Road\nSandton\n2057", "tax_number": "4460271002"}, headers=h)
    res = await api.put(
        "/settings/documents",
        json={"registration_number": "2009/106070/23", "phone": "011 555 0100", "website": "ids.example.com", "bank_name": "Standard Bank",
              "account_holder": "Intermediate Data Systems", "account_number": "372291600", "account_type": "Business Current Account",
              "branch_name": "Centurion Lifestyle", "branch_code": "002645", "swift_code": "SBZAZAJJ"},
        headers=h,
    )
    assert res.status_code == 200, res.text
    customer = (await api.post("/customers", json={"name": "Bayajula Services PTY LTD", "billing_address": "246 Jean Avenue\nCity of Tshwane\n0157",
                                                    "delivery_address": "Gate 3, 246 Jean Avenue\nCity of Tshwane", "tax_number": "4999999999", "phone": "012 555 0199"}, headers=h)).json()
    assert customer["delivery_address"].startswith("Gate 3")
    await api.post(f"/customers/{customer['id']}/contacts", json={"first_name": "Sipho", "last_name": "Nkosi", "job_title": "Procurement", "is_primary": True}, headers=h)

    inv = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": TODAY, "reference": "Freshdesk renewal (4 licences)", "items": ITEM}, headers=h)).json()
    html = (await api.get(f"/invoices/{inv['id']}/document", headers=h)).text
    for text in ("Intermediate Data Systems", "96 Rivonia Road", "4460271002", "2009/106070/23", "011 555 0100", "ids.example.com",
                 "Bayajula Services PTY LTD", "246 Jean Avenue", "4999999999", "012 555 0199", "Gate 3", "Delivery address",
                 "Attention:", "Sipho Nkosi", "Procurement", "Freshdesk renewal (4 licences)",
                 "Standard Bank", "372291600", "Centurion Lifestyle", "002645", "65"):
        assert text in html, text
    assert "Prepared by" not in html  # who made it shows in the app, not on paper
    assert inv["created_by"] == str(owner["user_id"])

    quote = (await api.post("/quotes", json={"customer_id": customer["id"], "issue_date": TODAY, "title": "Freshdesk renewal 2027",
                                               "description": "Annual renewal of four Omnichannel Pro licences,\nwith the bot builder included.", "items": ITEM}, headers=h)).json()
    assert quote["title"] == "Freshdesk renewal 2027"
    qhtml = (await api.get(f"/quotes/{quote['id']}/document", headers=h)).text
    assert "Freshdesk renewal 2027" in qhtml and "with the bot builder included." in qhtml and "Sipho Nkosi" in qhtml
    edited = (await api.patch(f"/quotes/{quote['id']}", json={"title": "Freshdesk renewal 2027 (revised)", "description": ""}, headers=h)).json()
    assert edited["title"] == "Freshdesk renewal 2027 (revised)" and edited["description"] is None


@pytest.mark.asyncio
async def test_purchase_order_shows_where_to_deliver_and_who_ordered(api):
    owner = await new_company(api, "Order Co")
    h = owner["headers"]
    await api.patch("/settings", json={"address": "7 Main Road\nMidrand\n1685"}, headers=h)
    assert (await api.get("/company", headers=h)).json()["address"].startswith("7 Main Road")
    supplier = (await api.post("/suppliers", json={"name": "Fresh Farms", "contact_name": "Pieter van Wyk", "phone": "021 555 0199"}, headers=h)).json()
    po = (await api.post("/purchase-orders", json={"supplier_id": supplier["id"], "issue_date": TODAY, "items": ITEM}, headers=h)).json()
    html = (await api.get(f"/purchase-orders/{po['id']}/document", headers=h)).text
    assert "Deliver to" in html and "7 Main Road" in html  # no address given: the company's own
    assert "Prepared by" not in html and po["created_by"] == str(owner["user_id"])
    assert "Attention:" in html and "Pieter van Wyk" in html and "021 555 0199" in html

    site = (await api.post("/purchase-orders", json={"supplier_id": supplier["id"], "issue_date": TODAY, "delivery_address": "Gate 2, Kyalami Estate", "items": ITEM}, headers=h)).json()
    html = (await api.get(f"/purchase-orders/{site['id']}/document", headers=h)).text
    assert "Gate 2, Kyalami Estate" in html
