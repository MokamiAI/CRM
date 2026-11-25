"""Companies outside South Africa: the country picked at sign-up sets the
currency, tax, time zone, financial year and what the tax number is called;
each can be changed in Settings, and documents follow them. YGT's own
subscriptions stay in rand."""
import uuid
from zoneinfo import ZoneInfo

import pytest

from app.core.countries import COUNTRIES, CURRENCIES
from app.services.channel_providers import normalize_phone

from .conftest import ADDRESS, mark_verified


async def sign_up(api, name, country=None):
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    body = {"company_name": name, "full_name": "Test Owner", "email": email, "password": "Correct-Horse-9",
            "business_address": ADDRESS, "accept_terms": True}
    if country:
        body["country"] = country
    res = await api.post("/auth/register", json=body)
    assert res.status_code == 201, res.text
    await mark_verified(email)
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_every_country_has_a_real_time_zone_and_currency():
    assert len(COUNTRIES) == 55  # Africa's 54 and "another country"
    for c in COUNTRIES.values():
        ZoneInfo(c.timezone)
        assert c.currency in CURRENCIES and 0 <= c.tax_rate <= 50 and 1 <= c.fy_start <= 12
    assert {"USD", "EUR", "GBP", "ZAR", "KES", "NGN", "GHS"} <= set(CURRENCIES)


def test_local_numbers_get_the_companys_dialling_code():
    assert normalize_phone("082 123 4567") == "27821234567"
    assert normalize_phone("0712 345 678", "254") == "254712345678"
    assert normalize_phone("+234 803 123 4567", "254") == "2348031234567"
    assert normalize_phone("0712 345 678", "") is None  # another country: needs its +code


@pytest.mark.asyncio
async def test_public_country_list(api):
    res = await api.get("/public/countries")
    assert res.status_code == 200
    kenya = next(c for c in res.json()["countries"] if c["code"] == "KE")
    assert kenya == {"code": "KE", "name": "Kenya", "currency": "KES", "dial": "254", "timezone": "Africa/Nairobi",
                     "tax_rate": "16", "tax_name": "VAT", "tax_id": "KRA PIN", "fy_start": 1}


@pytest.mark.asyncio
async def test_sign_up_without_a_country_is_south_african(api):
    h = await sign_up(api, "Polokwane Plumbing")
    company = (await api.get("/settings", headers=h)).json()
    assert (company["country"], company["default_currency"], company["default_timezone"]) == ("ZA", "ZAR", "Africa/Johannesburg")
    assert (company["tax_name"], float(company["default_tax_rate"]), company["financial_year_start_month"]) == ("VAT", 15, 3)
    assert (await api.get("/settings/documents", headers=h)).json()["tax_label"] == "VAT number"


@pytest.mark.asyncio
async def test_a_kenyan_company_invoices_in_shillings_with_its_kra_pin(api):
    h = await sign_up(api, "Nairobi IT Services", "ke")
    company = (await api.get("/company", headers=h)).json()
    assert (company["country"], company["default_currency"], company["tax_name"], float(company["default_tax_rate"])) == ("KE", "KES", "VAT", 16)
    settings = (await api.get("/settings", headers=h)).json()
    assert (settings["default_timezone"], settings["financial_year_start_month"]) == ("Africa/Nairobi", 1)
    assert (await api.get("/settings/documents", headers=h)).json()["tax_label"] == "KRA PIN"

    await api.patch("/settings", json={"vat_registered": True, "tax_number": "P051234567X"}, headers=h)
    customer = (await api.post("/customers", json={"name": "Westlands Office Park", "tax_number": "P059876543Z"}, headers=h)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-11-25", "due_date": "2026-12-25",
                                                 "items": [{"description": "Managed IT support (monthly)", "quantity": "1", "unit_price": "50000", "tax_rate": "16"}]}, headers=h)).json()
    assert invoice["total"] == "58000.00"
    html = (await api.get(f"/invoices/{invoice['id']}/document", headers=h)).text
    assert "KES 58,000.00" in html and "KRA PIN" in html and "P051234567X" in html and "Total incl. VAT" in html
    assert "ZAR" not in html  # no rand on a Kenyan invoice


@pytest.mark.asyncio
async def test_gst_country_documents_say_gst(api):
    h = await sign_up(api, "Monrovia Supplies", "LR")
    await api.patch("/settings", json={"vat_registered": True, "tax_number": "500123"}, headers=h)
    customer = (await api.post("/customers", json={"name": "Port Client"}, headers=h)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-11-25", "due_date": "2026-12-25",
                                                 "items": [{"description": "Cables", "quantity": "2", "unit_price": "100", "tax_rate": "10"}]}, headers=h)).json()
    html = (await api.get(f"/invoices/{invoice['id']}/document", headers=h)).text
    assert "LRD 220.00" in html and "Total excl. GST" in html and "Total incl. VAT" not in html


@pytest.mark.asyncio
async def test_changing_country_renames_the_tax_number_unless_customised(api):
    h = await sign_up(api, "Moving North", "KE")
    res = await api.patch("/settings", json={"country": "NG", "default_currency": "NGN", "tax_name": "VAT", "default_tax_rate": "7.5",
                                             "default_timezone": "Africa/Lagos"}, headers=h)
    assert res.status_code == 200, res.text
    assert (res.json()["country"], res.json()["default_currency"], float(res.json()["default_tax_rate"])) == ("NG", "NGN", 7.5)
    assert (await api.get("/settings/documents", headers=h)).json()["tax_label"] == "TIN"

    # Their own label stays when the country changes again.
    template = (await api.get("/settings/documents", headers=h)).json()
    assert (await api.put("/settings/documents", json={**template, "tax_label": "FIRS TIN"}, headers=h)).status_code == 200
    await api.patch("/settings", json={"country": "GH"}, headers=h)
    assert (await api.get("/settings/documents", headers=h)).json()["tax_label"] == "FIRS TIN"


@pytest.mark.asyncio
async def test_settings_reject_unknown_country_currency_and_time_zone(api):
    h = await sign_up(api, "Typo Traders")
    for body in ({"country": "XY"}, {"default_currency": "RAND"}, {"default_timezone": "Africa/Atlantis"}, {"default_tax_rate": "75"}):
        assert (await api.patch("/settings", json=body, headers=h)).status_code == 422, body
    assert (await api.patch("/settings", json={"default_currency": "usd"}, headers=h)).json()["default_currency"] == "USD"
    bad = await api.post("/auth/register", json={"company_name": "X", "full_name": "Y", "email": f"{uuid.uuid4().hex[:8]}@example.com",
                                                "password": "Correct-Horse-9", "business_address": ADDRESS, "accept_terms": True, "country": "XY"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_subscription_prices_stay_in_rand(api):
    h = await sign_up(api, "Lagos Logistics", "NG")
    nigerian = (await api.get("/billing/plans", headers=h)).json()
    south_african = (await api.get("/billing/plans", headers=await sign_up(api, "Pretoria Plumbing"))).json()
    assert nigerian and nigerian == south_african  # same rand prices wherever the company is
