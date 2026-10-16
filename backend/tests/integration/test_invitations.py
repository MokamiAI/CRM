"""Inviting a team member: added with a name, email and role (no
password); they get a link, choose their own password and are signed in,
with their email confirmed. The link works once; the admin can resend it."""
import re
import uuid

import pytest

from .conftest import new_company


def _invite_token(api, before: int) -> str:
    """The token in the invitation email that was just queued."""
    for name, args in api.queued[before:]:
        if name.endswith("send_platform_email_task"):
            m = re.search(r"/invite\?token=([\w-]+)", args[0]["text"])
            if m:
                return m.group(1)
    raise AssertionError("no invitation email queued")


@pytest.mark.asyncio
async def test_invite_set_password_and_sign_in(api):
    owner = await new_company(api, "Invite Catering")
    email = f"lerato-{uuid.uuid4().hex[:6]}@example.com"
    before = len(api.queued)
    res = await api.post("/users", json={"email": email, "full_name": "Lerato Dube", "role": "staff"}, headers=owner["headers"])
    assert res.status_code == 201, res.text
    member = res.json()
    assert member["invite_pending"] is True
    token = _invite_token(api, before)

    # They can't sign in before choosing a password.
    assert (await api.post("/auth/login", json={"email": email, "password": "anything-at-all"})).status_code == 401

    # The page greets them.
    info = (await api.get("/auth/invite", params={"token": token})).json()
    assert info == {"full_name": "Lerato Dube", "email": email, "company_name": "Invite Catering"}

    # Too short a password is refused; a good one signs them in.
    assert (await api.post("/auth/invite", json={"token": token, "password": "short"})).status_code == 422
    res = await api.post("/auth/invite", json={"token": token, "password": "Correct-Horse-9"})
    assert res.status_code == 200, res.text
    me = (await api.get("/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"})).json()
    assert me["email"] == email and me["email_verified_at"] and me["invite_pending"] is False and me["verify_by"] is None

    # The link is spent; their own password works from now on.
    again = await api.post("/auth/invite", json={"token": token, "password": "Another-Horse-9"})
    assert again.status_code == 400 and again.json()["error_code"] == "INVITE_LINK_INVALID"
    assert (await api.post("/auth/login", json={"email": email, "password": "Correct-Horse-9"})).status_code == 200
    team = {u["email"]: u["invite_pending"] for u in (await api.get("/users", headers=owner["headers"])).json()}
    assert team[email] is False


@pytest.mark.asyncio
async def test_resend_invite_and_bad_links(api):
    owner = await new_company(api, "Resend Co")
    email = f"sipho-{uuid.uuid4().hex[:6]}@example.com"
    member = (await api.post("/users", json={"email": email, "full_name": "Sipho N", "role": "staff"}, headers=owner["headers"])).json()
    before = len(api.queued)
    res = await api.post(f"/users/{member['id']}/invite", headers=owner["headers"])
    assert res.status_code == 200, res.text
    token = _invite_token(api, before)
    assert (await api.post("/auth/invite", json={"token": token, "password": "Correct-Horse-9"})).status_code == 200
    # Joined: nothing to resend.
    assert (await api.post(f"/users/{member['id']}/invite", headers=owner["headers"])).json()["error_code"] == "INVITE_ALREADY_ACCEPTED"
    # Made-up link.
    assert (await api.get("/auth/invite", params={"token": "x" * 40})).json()["error_code"] == "INVITE_LINK_INVALID"
    # Another company can't resend this company's invitations.
    other = await new_company(api, "Elsewhere")
    assert (await api.post(f"/users/{member['id']}/invite", headers=other["headers"])).status_code == 404
