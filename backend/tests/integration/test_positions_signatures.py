"""Each person's position (set by an admin or themselves), shown to the
team; and the signature made for them from it and the company's details
when they haven't written one."""
from types import SimpleNamespace

import pytest

from app.services.signatures import signature_for, suggested_signature

from .conftest import new_company
from .test_team_tasks import _member


@pytest.mark.asyncio
async def test_position_is_set_by_admin_or_self_and_shown_to_the_team(api):
    admin = await new_company(api, "Positions Co")
    staff, staff_id = await _member(api, admin)
    res = await api.patch(f"/users/{staff_id}", json={"job_title": "  Sales Manager "}, headers=admin["headers"])
    assert res.status_code == 200 and res.json()["job_title"] == "Sales Manager"
    me = await api.patch("/auth/me", json={"job_title": "Head of Sales"}, headers=staff)
    assert me.json()["job_title"] == "Head of Sales"
    team = {p["id"]: p for p in (await api.get("/team", headers=admin["headers"])).json()}
    assert team[staff_id]["job_title"] == "Head of Sales"
    assert (await api.patch("/auth/me", json={"job_title": ""}, headers=staff)).json()["job_title"] is None


@pytest.mark.asyncio
async def test_company_phone_and_website_are_saved(api):
    admin = await new_company(api, "Contact Co")
    res = await api.patch("/settings", json={"phone": "012 345 6789", "website": "democatering.co.za"}, headers=admin["headers"])
    assert res.status_code == 200, res.text
    assert res.json()["phone"] == "012 345 6789" and res.json()["website"] == "democatering.co.za"
    # Everyone sees them, for their suggested signature.
    profile = (await api.get("/company", headers=admin["headers"])).json()
    assert profile["phone"] == "012 345 6789"


def test_the_signature_falls_back_from_theirs_to_the_company_to_a_suggestion():
    company = SimpleNamespace(company_name="Demo Catering Co", phone="012 345 6789", website="democatering.co.za", email_signature=None)
    user = SimpleNamespace(full_name="Thandi Mokoena", job_title="Sales Manager", email="thandi@example.com", email_signature=None)
    assert suggested_signature(user, company) == "Thandi Mokoena\nSales Manager · Demo Catering Co\nthandi@example.com\n012 345 6789\ndemocatering.co.za"
    assert signature_for(user, company) == suggested_signature(user, company)
    company.email_signature = "The Demo team"
    assert signature_for(user, company) == "The Demo team"
    user.email_signature = "Thandi"
    assert signature_for(user, company) == "Thandi"
    # No position, no phone: just what there is.
    bare = SimpleNamespace(full_name="Sipho", job_title=None, email="s@example.com", email_signature=None)
    plain = SimpleNamespace(company_name="Acme", phone=None, website="", email_signature=None)
    assert suggested_signature(bare, plain) == "Sipho\nAcme\ns@example.com"


@pytest.mark.asyncio
async def test_the_quote_of_the_week_is_seen_once_per_person_not_per_browser(api):
    admin = await new_company(api, "Quote Seen Co")
    assert (await api.get("/auth/me", headers=admin["headers"])).json()["quote_seen"] is None
    await api.patch("/auth/me", json={"quote_seen": "2026-10-26"}, headers=admin["headers"])
    assert (await api.get("/auth/me", headers=admin["headers"])).json()["quote_seen"] == "2026-10-26"
