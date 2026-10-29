"""POPIA s69: prospects only get marketing once they've agreed, and may be asked once."""
import pytest

from app.services import prospect_service
from .conftest import new_company


@pytest.mark.asyncio
async def test_prospects_join_audiences_only_after_agreeing(api, monkeypatch):
    sent = []
    monkeypatch.setattr(prospect_service, "send_email", lambda config, email: sent.append(email))
    owner = await new_company(api, "Consent Co")
    h = owner["headers"]
    await api.post("/customers", json={"name": "Existing buyer", "email": "buyer@example.com"}, headers=h)
    cold = (await api.post("/prospects", json={"name": "Cold Lead", "email": "cold@example.com"}, headers=h)).json()
    warm = (await api.post("/prospects", json={"name": "Warm Lead", "email": "warm@example.com"}, headers=h)).json()

    audience = lambda: api.post("/marketing/audience/preview", json={"rules": []}, headers=h)
    assert (await audience()).json()["count"] == 1  # only the customer

    # A tick needs a "how"; with one, the prospect joins every audience.
    assert (await api.put(f"/marketing/prospects/{warm['id']}/consent", json={"agreed": True}, headers=h)).status_code == 400
    res = await api.put(f"/marketing/prospects/{warm['id']}/consent", json={"agreed": True, "source": "Said yes at the expo"}, headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["marketing_consent_source"] == "Said yes at the expo"
    assert (await audience()).json()["count"] == 2

    # The one-time invite: sent once, with a yes/no link; never twice.
    res = await api.post(f"/marketing/prospects/{cold['id']}/invite", json={"subject": "", "message": "Hi {name}, we'd love to keep in touch."}, headers=h)
    assert res.status_code == 200, res.text
    assert len(sent) == 1 and "Hi Cold," in sent[0].html
    again = await api.post(f"/marketing/prospects/{cold['id']}/invite", json={"message": "Hi again, just checking in."}, headers=h)
    assert again.status_code == 409 and again.json()["error_code"] == "PROSPECT_ALREADY_INVITED"
    assert (await audience()).json()["count"] == 2  # asking isn't agreeing

    # Their "yes" link records consent; "no" would opt them out.
    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system
    from app.models.customer import Customer

    async with AsyncSessionLocal() as db:
        set_system(db)
        token = (await db.get(Customer, __import__("uuid").UUID(cold["id"]))).consent_token
    page = await api.post(f"/public/m/c/{token}/yes")
    assert page.status_code == 200 and "keep you posted" in page.text
    assert (await audience()).json()["count"] == 3
    await api.post(f"/public/m/c/{token}/no")
    assert (await audience()).json()["count"] == 2

    listed = {p["name"]: p for p in (await api.get("/marketing/prospects", headers=h)).json()}
    assert set(listed) == {"Cold Lead", "Warm Lead"}
    assert listed["Cold Lead"]["marketing_opt_out"] is True and listed["Cold Lead"]["consent_invited_at"]
