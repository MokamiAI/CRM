"""Pipeline prospects must not appear as customers until a deal is Won."""
import pytest
from .conftest import new_company


@pytest.mark.asyncio
async def test_prospect_is_saved_in_pipeline_and_promoted_only_when_won(api):
    owner = await new_company(api, "Prospect Lifecycle")
    h = owner["headers"]
    other = await new_company(api, "Other Prospect Company")
    customer = await api.post("/customers", json={"name": "Established account"}, headers=h)
    assert customer.status_code == 201, customer.text
    prospect = await api.post("/prospects", json={"name": "Potential account", "contact": {
        "name": "Lerato Dube", "email": "lerato@example.com", "phone": "082 555 0101"
    }}, headers=h)
    assert prospect.status_code == 201, prospect.text
    account = prospect.json()
    pid = account["id"]
    assert account["is_prospect"] is True
    assert all(c["id"] != pid for c in (await api.get("/customers", headers=h)).json())
    assert all(c["id"] != pid for c in (await api.get("/reports/customers", headers=h)).json())
    summary = (await api.get("/reports/summary", headers=h)).json()
    assert summary["active_customers"] == 1
    accounts = (await api.get("/pipeline/accounts", headers=h)).json()
    assert {c["id"] for c in accounts} == {pid, customer.json()["id"]}
    assert (await api.get("/pipeline/accounts", headers=other["headers"])).json() == []
    assert (await api.get(f"/customers/{pid}/contacts", headers=other["headers"])).status_code == 404
    contacts = (await api.get(f"/customers/{pid}/contacts", headers=h)).json()
    assert contacts[0]["phone"] == "082 555 0101"
    res = await api.post("/deals", json={"title": "First opportunity", "customer_id": pid,
        "contact_id": contacts[0]["id"], "mcem_enabled": False}, headers=h)
    assert res.status_code == 201, res.text
    did = res.json()["id"]
    # Lost and reopened leads keep their details without becoming customers.
    assert (await api.patch(f"/deals/{did}", json={"stage": "lost"}, headers=h)).status_code == 200
    assert (await api.get(f"/customers/{pid}", headers=h)).json()["is_prospect"] is True
    assert (await api.patch(f"/deals/{did}", json={"stage": "lead"}, headers=h)).status_code == 200
    won = await api.patch(f"/deals/{did}", json={"stage": "won"}, headers=h)
    assert won.status_code == 200, won.text
    assert any(c["id"] == pid for c in (await api.get("/customers", headers=h)).json())
    assert (await api.get(f"/customers/{pid}", headers=h)).json()["is_prospect"] is False
    assert (await api.get(f"/customers/{pid}/contacts", headers=h)).json()[0]["id"] == contacts[0]["id"]
    # A later lost deal must not demote an established customer.
    await api.patch(f"/deals/{did}", json={"stage": "lost"}, headers=h)
    assert (await api.get(f"/customers/{pid}", headers=h)).json()["is_prospect"] is False


@pytest.mark.asyncio
async def test_creating_won_deal_promotes_prospect(api):
    owner = await new_company(api, "Won Prospect")
    h = owner["headers"]
    account = (await api.post("/prospects", json={"name": "Ready buyer"}, headers=h)).json()
    res = await api.post("/deals", json={"title": "Signed agreement", "customer_id": account["id"], "stage": "won"}, headers=h)
    assert res.status_code == 201, res.text
    assert (await api.get(f"/customers/{account['id']}", headers=h)).json()["is_prospect"] is False
