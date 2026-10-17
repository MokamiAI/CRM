"""A customer can be added with the person you deal with there (saved as
its main contact); a new help desk ticket gets an automatic reply, signed
"YGT Support", that never shows the team's private inbox."""
import pytest

from app.core.config import settings

from .conftest import new_company


@pytest.mark.asyncio
async def test_customer_with_contact_person(api):
    owner = await new_company(api, "Contacts Co")
    h = owner["headers"]
    res = await api.post("/customers", json={
        "name": "Acme Mining Ltd", "email": "accounts@acme.example.com",
        "contact": {"name": "Lerato van der Merwe", "job_title": "Procurement", "email": "lerato@acme.example.com", "phone": "082 555 0101"},
    }, headers=h)
    assert res.status_code == 201, res.text
    cid = res.json()["id"]
    contacts = (await api.get(f"/customers/{cid}/contacts", headers=h)).json()
    assert len(contacts) == 1
    c = contacts[0]
    assert (c["first_name"], c["last_name"], c["job_title"], c["email"], c["phone"], c["is_primary"]) == (
        "Lerato", "van der Merwe", "Procurement", "lerato@acme.example.com", "082 555 0101", True)

    # Editing the customer updates that same main contact (no duplicate).
    res = await api.patch(f"/customers/{cid}", json={"contact": {"name": "Lerato Dube", "email": "", "phone": "011 555 0199"}}, headers=h)
    assert res.status_code == 200, res.text
    contacts = (await api.get(f"/customers/{cid}/contacts", headers=h)).json()
    assert len(contacts) == 1 and contacts[0]["last_name"] == "Dube" and contacts[0]["email"] is None and contacts[0]["phone"] == "011 555 0199"

    # Without a contact person, nothing changes; a bad email is refused.
    assert (await api.post("/customers", json={"name": "Solo Trader"}, headers=h)).status_code == 201
    bad = await api.post("/customers", json={"name": "X Co", "contact": {"name": "Sam", "email": "not-an-email"}}, headers=h)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_new_ticket_gets_an_automatic_reply(api, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_EMAIL", "owner-private@gmail.com")
    owner = await new_company(api, "Help Me Co")
    before = len(api.queued)
    res = await api.post("/support/tickets", json={"subject": "Invoice PDF missing", "body": "The PDF does not attach."}, headers=owner["headers"])
    assert res.status_code == 201, res.text
    sent = [args[0] for name, args in api.queued[before:] if name.endswith("send_platform_email_task")]
    ack = next(e for e in sent if e["to"] == owner["email"])
    assert ack["subject"].startswith("We've received your ticket #") and ack["from_name"] == "YGT Support"
    assert "owner-private@gmail.com" not in ack["text"] + ack["html"] and "Reply-To" not in ack["headers"]
    # The team is still told, in its private inbox.
    assert any(e["to"] == "owner-private@gmail.com" for e in sent)
