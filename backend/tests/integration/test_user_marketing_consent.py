"""YGT's own marketing (POPIA s69): asked at sign-up, once in the app for
everyone else, changeable in the profile, and carried to YGT's workspace."""
import uuid

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.models.billing import SubscriberLink
from app.models.customer import Customer
from app.models.user import User
from app.services import subscriber_pipeline
from .conftest import ADDRESS, mark_verified, new_company


async def sign_up(api, name, **extra):
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    res = await api.post("/auth/register", json={
        "company_name": name, "full_name": "Test Owner", "email": email, "password": "Correct-Horse-9", "business_address": ADDRESS, **extra,
    })
    assert res.status_code == 201, res.text
    await mark_verified(email)
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def forget_answer(headers_email):
    """As if they signed up before YGT asked."""
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(User).where(User.email == headers_email).values(marketing_opt_in=None, marketing_opt_in_at=None, marketing_opt_in_source=None))
        await db.commit()


@pytest.mark.asyncio
async def test_sign_up_records_the_answer_and_never_ticks_it_for_them(api):
    yes = await sign_up(api, "Consent yes", marketing_opt_in=True)
    me = (await api.get("/auth/me", headers=yes)).json()
    assert me["marketing_opt_in"] is True
    left_empty = await sign_up(api, "Consent empty")
    assert (await api.get("/auth/me", headers=left_empty)).json()["marketing_opt_in"] is False
    # Answered at sign-up: not asked again.
    assert not [n for n in (await api.get("/notifications", headers=left_empty)).json()["items"] if n["kind"] == "marketing_consent"]


@pytest.mark.asyncio
async def test_people_who_werent_asked_get_one_question_in_the_app(api):
    owner = await new_company(api, "Consent unasked")
    await forget_answer(owner["email"])
    headers = owner["headers"]
    assert (await api.get("/auth/me", headers=headers)).json()["marketing_opt_in"] is None
    for _ in range(2):  # asked once, however often the bell checks
        asked = [n for n in (await api.get("/notifications", headers=headers)).json()["items"] if n["kind"] == "marketing_consent"]
        assert len(asked) == 1 and asked[0]["read_at"] is None
    res = await api.patch("/auth/me", headers=headers, json={"marketing_opt_in": True, "marketing_source": "prompt"})
    assert res.status_code == 200 and res.json()["marketing_opt_in"] is True
    asked = [n for n in (await api.get("/notifications", headers=headers)).json()["items"] if n["kind"] == "marketing_consent"]
    assert asked[0]["read_at"] is not None
    async with AsyncSessionLocal() as db:
        set_system(db)
        user = await db.scalar(select(User).where(User.email == owner["email"]))
        assert user.marketing_opt_in_source == "prompt" and user.marketing_opt_in_at is not None
    # Saving the profile without the answer leaves it as it was.
    await api.patch("/auth/me", headers=headers, json={"full_name": "Renamed Owner"})
    assert (await api.get("/auth/me", headers=headers)).json()["marketing_opt_in"] is True


@pytest.mark.asyncio
async def test_the_answer_reaches_ygts_workspace_and_a_newer_one_replaces_it(api, monkeypatch):
    ygt = await new_company(api, "YGT Consent HQ")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", ygt["email"])
    owner = await new_company(api, "Consent subscriber")
    await forget_answer(owner["email"])

    async def sync_and_read():
        async with AsyncSessionLocal() as db:
            await subscriber_pipeline.sync(db, only={owner["company_id"]})
            await db.commit()
        async with AsyncSessionLocal() as db:
            set_system(db)
            link = await db.get(SubscriberLink, owner["company_id"])
            return await db.get(Customer, link.customer_id)

    customer = await sync_and_read()
    assert customer.is_prospect and customer.marketing_consent_at is None and not customer.marketing_opt_out  # not asked yet: nothing

    await api.patch("/auth/me", headers=owner["headers"], json={"marketing_opt_in": True, "marketing_source": "prompt"})
    customer = await sync_and_read()
    assert customer.marketing_consent_at is not None and "prompt" in customer.marketing_consent_source and not customer.marketing_opt_out

    await api.patch("/auth/me", headers=owner["headers"], json={"marketing_opt_in": False})
    customer = await sync_and_read()
    assert customer.marketing_opt_out
