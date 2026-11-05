"""Costs and bills by permission: the account owner sees and manages them
and decides who else may (view, or manage); nobody else can, other admins
included; the owner stays an admin until they hand the account over."""
import uuid
from datetime import date

import pytest

from .conftest import mark_verified, new_company

TODAY = date.today().isoformat()
BILL = {"description": "Salaries", "category": "salaries", "amount": "25000", "due_date": TODAY}


async def member(api, h, role):
    email = f"{uuid.uuid4().hex[:10]}@example.com"
    person = (await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": role.title(), "role": role}, headers=h)).json()
    await mark_verified(email)
    token = (await api.post("/auth/login", json={"email": email, "password": "Correct-Horse-9"})).json()["access_token"]
    return person, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_only_the_owner_and_those_allowed_see_costs(api):
    owner = await new_company(api, "Owned Co")
    h = owner["headers"]
    me = (await api.get("/auth/me", headers=h)).json()
    assert me["is_account_owner"] is True
    assert (await api.post("/costs", json=BILL, headers=h)).status_code == 201

    admin, ah = await member(api, h, "admin")
    manager, mh = await member(api, h, "manager")
    # Another admin, and a manager, see nothing until the owner allows it.
    for headers in (ah, mh):
        refused = await api.get("/costs", headers=headers)
        assert refused.status_code == 403 and refused.json()["error_code"] == "COSTS_NO_ACCESS"
    # Only the owner can give access, and other admins can't give it themselves.
    assert (await api.put(f"/users/{admin['id']}/cost-access", json={"cost_access": "manage"}, headers=ah)).status_code == 403

    # View: read everything, change nothing.
    assert (await api.put(f"/users/{manager['id']}/cost-access", json={"cost_access": "view"}, headers=h)).json()["cost_access"] == "view"
    assert (await api.get("/costs", headers=mh)).status_code == 200
    assert (await api.get("/costs/summary", headers=mh)).status_code == 200
    viewing = await api.post("/costs", json=BILL, headers=mh)
    assert viewing.status_code == 403 and viewing.json()["error_code"] == "COSTS_VIEW_ONLY"

    # Manage: add and change too.
    await api.put(f"/users/{admin['id']}/cost-access", json={"cost_access": "manage"}, headers=h)
    assert (await api.post("/costs", json=BILL, headers=ah)).status_code == 201

    # Taken away again.
    await api.put(f"/users/{manager['id']}/cost-access", json={"cost_access": "none"}, headers=h)
    assert (await api.get("/costs", headers=mh)).status_code == 403

    # A viewer can be given view access only.
    viewer, _ = await member(api, h, "viewer")
    assert (await api.put(f"/users/{viewer['id']}/cost-access", json={"cost_access": "manage"}, headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_the_owner_hands_over_and_cant_be_demoted(api):
    owner = await new_company(api, "Handover Co")
    h = owner["headers"]
    me = (await api.get("/auth/me", headers=h)).json()
    admin, ah = await member(api, h, "admin")
    staff, sh = await member(api, h, "staff")

    # Another admin can't demote or switch off the owner.
    locked = await api.patch(f"/users/{me['id']}", json={"role": "staff"}, headers=ah)
    assert locked.status_code == 409 and locked.json()["error_code"] == "OWNER_LOCKED"
    assert (await api.patch(f"/users/{me['id']}", json={"is_active": False}, headers=ah)).status_code == 409

    # Only an active admin can become owner, and only the owner can hand over.
    assert (await api.post(f"/users/{staff['id']}/make-owner", headers=h)).status_code == 409
    assert (await api.post(f"/users/{admin['id']}/make-owner", headers=ah)).status_code == 403
    handed = await api.post(f"/users/{admin['id']}/make-owner", headers=h)
    assert handed.status_code == 200 and handed.json()["is_account_owner"] is True

    after = (await api.get("/auth/me", headers=h)).json()
    assert after["is_account_owner"] is False and after["cost_access"] == "manage"  # still manages costs
    assert (await api.get("/costs", headers=ah)).status_code == 200
    # The new owner now decides: the former owner can't give access any more.
    assert (await api.put(f"/users/{staff['id']}/cost-access", json={"cost_access": "view"}, headers=h)).status_code == 403
    assert (await api.put(f"/users/{staff['id']}/cost-access", json={"cost_access": "view"}, headers=ah)).status_code == 200
    assert (await api.get("/costs", headers=sh)).status_code == 200
