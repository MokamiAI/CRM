"""Each deal has a priority (high, medium or low): set when it's made,
changed later, and only those three accepted."""
import pytest

from .conftest import new_company


@pytest.mark.asyncio
async def test_deals_carry_a_priority(api):
    owner = await new_company(api, "Priority Catering")
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Naledi Events"}, headers=h)).json()

    plain = (await api.post("/deals", json={"title": "Birthday platters", "customer_id": customer["id"]}, headers=h)).json()
    assert plain["priority"] == "medium"  # the default
    big = await api.post("/deals", json={"title": "Wedding, 120 guests", "customer_id": customer["id"], "priority": "high"}, headers=h)
    assert big.status_code == 201, big.text
    assert big.json()["priority"] == "high"

    changed = await api.patch(f"/deals/{plain['id']}", json={"priority": "low"}, headers=h)
    assert changed.status_code == 200 and changed.json()["priority"] == "low"
    listed = {d["title"]: d["priority"] for d in (await api.get("/deals", headers=h)).json()}
    assert listed == {"Birthday platters": "low", "Wedding, 120 guests": "high"}

    for bad in ("urgent", "", "HIGH"):
        assert (await api.patch(f"/deals/{plain['id']}", json={"priority": bad}, headers=h)).status_code == 422
