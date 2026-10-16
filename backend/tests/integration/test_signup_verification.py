"""Signing up needs a business address and a real email. The account
works at once, but its email must be confirmed within 48 hours to keep
access: after that only sign-in, "who am I" and resending the link work
until the link in "Confirm your email" is clicked."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from email_validator import EmailNotValidError
from sqlalchemy import update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_email_token
from app.core.tenancy import set_system
from app.models.user import User
from app.services import email_check, verification_service

from .conftest import ADDRESS

SIGNUP = {"company_name": "Proof Catering", "full_name": "Lerato Mokoena", "password": "Correct-Horse-9", "business_address": ADDRESS}


def _email() -> str:
    return f"{uuid.uuid4().hex[:12]}@example.com"


async def _age(email: str, hours: int) -> None:
    """Pretend the account was made this many hours ago."""
    async with AsyncSessionLocal() as db:
        set_system(db)
        made = datetime.now(timezone.utc) - timedelta(hours=hours)
        await db.execute(update(User).where(User.email == email).values(created_at=made))
        await db.commit()


@pytest.mark.asyncio
async def test_48_hours_to_confirm_then_the_door_closes_until_the_link_is_clicked(api, monkeypatch):
    # As if the rule had always been there (accounts from before it get 48
    # hours from its start; see verification_service.RULE_STARTED).
    monkeypatch.setattr(verification_service, "RULE_STARTED", datetime(2000, 1, 1, tzinfo=timezone.utc))
    email = _email()
    res = await api.post("/auth/register", json={**SIGNUP, "email": email})
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # Straight in: the system works, and says by when to confirm.
    me = (await api.get("/auth/me", headers=headers)).json()
    assert me["email_verified_at"] is None
    left = datetime.fromisoformat(me["verify_by"]) - datetime.now(timezone.utc)
    assert timedelta(hours=47) < left <= timedelta(hours=48)
    assert (await api.get("/customers", headers=headers)).status_code == 200
    company = (await api.get("/settings", headers=headers)).json()
    assert company["address"] == ADDRESS
    # Saving a setting (e.g. closing the tour) keeps the deadline in the reply.
    saved = (await api.patch("/auth/me", json={"tour_completed": True}, headers=headers)).json()
    assert saved["verify_by"] == me["verify_by"]

    # 47 hours on: still open.
    await _age(email, 47)
    assert (await api.get("/customers", headers=headers)).status_code == 200

    # 49 hours on, not confirmed: everything outside /auth is refused.
    await _age(email, 49)
    for path in ("/customers", "/settings", "/invoices"):
        blocked = await api.get(path, headers=headers)
        assert blocked.status_code == 403 and blocked.json()["error_code"] == "EMAIL_NOT_VERIFIED", path
    assert (await api.post("/customers", json={"name": "Sneaky"}, headers=headers)).status_code == 403
    # They can still sign in, see who they are, and ask for the link again.
    assert (await api.post("/auth/login", json={"email": email, "password": SIGNUP["password"]})).status_code == 200
    assert (await api.get("/auth/me", headers=headers)).status_code == 200
    assert (await api.post("/auth/verify-email/resend", headers=headers)).status_code == 202

    # The link: open again, for good.
    token = create_email_token(me["id"], email)
    assert (await api.post("/auth/verify-email", json={"token": token})).status_code == 204
    assert (await api.get("/customers", headers=headers)).status_code == 200
    assert (await api.get("/auth/me", headers=headers)).json()["verify_by"] is None


@pytest.mark.asyncio
async def test_accounts_from_before_the_rule_get_48_hours_from_its_start(api, monkeypatch):
    monkeypatch.setattr(verification_service, "RULE_STARTED", datetime.now(timezone.utc) - timedelta(hours=1))
    email = _email()
    res = await api.post("/auth/register", json={**SIGNUP, "email": email})
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    await _age(email, 24 * 30)  # signed up a month ago, never confirmed
    assert (await api.get("/customers", headers=headers)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("address", [None, "", "Polokwane", "12345678901"])
async def test_a_business_address_is_required(api, address):
    body = {**SIGNUP, "email": _email()}
    if address is None:
        body.pop("business_address")
    else:
        body["business_address"] = address
    assert (await api.post("/auth/register", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_throwaway_inboxes_are_refused(api):
    res = await api.post("/auth/register", json={**SIGNUP, "email": f"{uuid.uuid4().hex[:8]}@mailinator.com"})
    assert res.status_code == 400 and res.json()["error_code"] == "EMAIL_DISPOSABLE"


@pytest.mark.asyncio
async def test_a_domain_that_cannot_receive_mail_is_refused(api, monkeypatch):
    # The real check asks DNS for the domain's mail servers; stand it in.
    monkeypatch.setattr(settings, "CHECK_EMAIL_DOMAINS", True)

    def fake_validate(email, **_):
        if email.endswith("@gmial.com"):
            raise EmailNotValidError("The domain name gmial.com does not accept email.")
        return email

    monkeypatch.setattr(email_check, "validate_email", fake_validate)
    bad = await api.post("/auth/register", json={**SIGNUP, "email": f"{uuid.uuid4().hex[:8]}@gmial.com"})
    assert bad.status_code == 400 and bad.json()["error_code"] == "EMAIL_UNDELIVERABLE"
    good = await api.post("/auth/register", json={**SIGNUP, "email": _email()})
    assert good.status_code == 201, good.text
