import pytest
from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.services.notification_service import NotificationService
from .conftest import new_company


@pytest.mark.asyncio
async def test_prospect_email_acceptance_updates_pipeline_once(api):
    import re
    import uuid
    owner = await new_company(api, "Email acceptance")
    h = owner["headers"]
    account = (await api.post("/prospects", headers=h, json={
        "name": "Prospect", "contact": {"name": "Buyer", "email": "buyer@example.com"}
    })).json()
    contacts = (await api.get(f"/customers/{account['id']}/contacts", headers=h)).json()
    deal = (await api.post("/deals", headers=h, json={
        "title": "Prospect sale", "customer_id": account["id"], "contact_id": contacts[0]["id"]
    })).json()
    quote = (await api.post("/quotes", headers=h, json={
        "customer_id": account["id"], "deal_id": deal["id"], "issue_date": "2026-10-19",
        "items": [{"description": "Service", "quantity": "1", "unit_price": "100", "tax_rate": "15"}]
    })).json()
    sent = await api.post(f"/quotes/{quote['id']}/send?notify=false", headers=h)
    assert sent.status_code == 200, sent.text
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_quote_sent(uuid.UUID(quote["id"]))
    assert email.to == "buyer@example.com"
    url = re.search(r'href="([^"]+/public/quotes/accept/[^"]+)"', email.html).group(1)
    path = url[url.index('/public/'):]
    assert (await api.get(path)).status_code == 200
    assert (await api.get(f"/deals/{deal['id']}", headers=h)).json()["stage"] == "lead"
    for _ in range(2):
        response = await api.post(path)
        assert response.status_code == 200, response.text
    assert (await api.get(f"/deals/{deal['id']}", headers=h)).json()["stage"] == "won"
    assert (await api.get(f"/customers/{account['id']}", headers=h)).json()["is_prospect"] is False
    assert len((await api.get("/invoices", headers=h)).json()) == 1
    assert (await api.post(path + "tampered")).status_code == 401
