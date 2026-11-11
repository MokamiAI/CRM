"""Admins, and YGT support, can email someone a link to choose a new
password; they never set it themselves. Only within their own company,
only to people who have joined, and not again within a few minutes."""
import uuid

import pytest

from app.core.config import settings

from .conftest import new_company
from .test_cost_access import member


def reset_emails(api, to):
    return [args[0] for name, args in api.queued if name.endswith("send_platform_email_task") and args[0]["to"] == to and "reset-password?token=" in str(args[0])]


@pytest.mark.asyncio
async def test_an_admin_sends_a_reset_link(api):
    owner = await new_company(api, "Reset Co")
    h = owner["headers"]
    staff, sh = await member(api, h, "staff")
    admin, ah = await member(api, h, "admin")
    me = (await api.get("/auth/me", headers=h)).json()

    assert (await api.post(f"/users/{staff['id']}/password-reset", headers=h)).status_code == 202
    sent = reset_emails(api, staff["email"])
    assert len(sent) == 1 and "sent you a link to choose a new password" in str(sent[0])

    # Not again straight away: no flooding someone's inbox.
    again = await api.post(f"/users/{staff['id']}/password-reset", headers=h)
    assert again.status_code == 429 and again.json()["error_code"] == "RESET_RECENTLY_SENT"

    # Another admin may send one to the owner: it only reaches the owner's inbox.
    assert (await api.post(f"/users/{me['id']}/password-reset", headers=ah)).status_code == 202

    # Staff can't, and nobody can reach another company's people.
    assert (await api.post(f"/users/{admin['id']}/password-reset", headers=sh)).status_code == 403
    other = await new_company(api, "Other Co")
    assert (await api.post(f"/users/{staff['id']}/password-reset", headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_not_for_someone_invited_or_deactivated(api):
    owner = await new_company(api, "Invite Co")
    h = owner["headers"]
    invited = (await api.post("/users", json={"email": f"{uuid.uuid4().hex[:10]}@example.com", "full_name": "Invited", "role": "staff"}, headers=h)).json()
    pending = await api.post(f"/users/{invited['id']}/password-reset", headers=h)
    assert pending.status_code == 400 and pending.json()["error_code"] == "INVITE_PENDING"

    staff, _ = await member(api, h, "staff")
    await api.patch(f"/users/{staff['id']}", json={"is_active": False}, headers=h)
    off = await api.post(f"/users/{staff['id']}/password-reset", headers=h)
    assert off.status_code == 400 and off.json()["error_code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_ygt_support_sends_a_reset_link(api, monkeypatch):
    support = await new_company(api, "YGT")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", support["email"])
    client = await new_company(api, "Locked Out Co")
    me = (await api.get("/auth/me", headers=client["headers"])).json()

    url = f"/admin/tenants/{client['company_id']}/people/{me['id']}/password-reset"
    assert (await api.post(url, headers=client["headers"])).status_code == 403
    assert (await api.post(url, headers=support["headers"])).status_code == 202
    assert "YGT support sent you a link" in str(reset_emails(api, me["email"])[0])

    # The person must belong to the company named in the address.
    wrong = f"/admin/tenants/{support['company_id']}/people/{me['id']}/password-reset"
    assert (await api.post(wrong, headers=support["headers"])).status_code == 404
