"""Nobody is removed to fit a plan: a trial team bigger than Hustle's 3
people keeps everyone, and Hustle can't be bought until it fits; Grow or
Scale (per seat) is the way on."""
import uuid

import pytest

from .conftest import new_company


@pytest.mark.asyncio
async def test_hustle_refused_for_four_people(api):
    owner = await new_company(api, "Big Trial Co")
    for name in ("Ann", "Ben", "Cas"):
        email = f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com"
        res = await api.post("/users", json={"email": email, "full_name": name, "role": "staff"}, headers=owner["headers"])
        assert res.status_code == 201, res.text

    billing = (await api.get("/billing", headers=owner["headers"])).json()
    assert billing["state"] == "trialing" and billing["usage"]["users"] == 4

    res = await api.post("/billing/checkout", json={"plan": "hustle", "interval": "monthly", "users": 1}, headers=owner["headers"])
    assert res.status_code == 400 and res.json()["error_code"] == "BILLING_PLAN_TOO_SMALL", res.text
    # Everyone is still on the team.
    assert len((await api.get("/users", headers=owner["headers"])).json()) == 4
