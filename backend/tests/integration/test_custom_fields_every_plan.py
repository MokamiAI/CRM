"""Custom fields are in every plan, Hustle included."""
import pytest

from .conftest import new_company


@pytest.mark.asyncio
@pytest.mark.parametrize("plan", ["hustle", "grow", "scale"])
async def test_every_plan_can_add_a_custom_field(api, plan):
    owner = await new_company(api, f"Fields {plan.title()}", plan=plan)
    res = await api.post("/custom-fields", json={"entity": "customer", "label": "Industry", "field_type": "text"}, headers=owner["headers"])
    assert res.status_code == 201, res.text
    listed = (await api.get("/custom-fields", params={"entity": "customer"}, headers=owner["headers"])).json()
    assert [f["label"] for f in listed] == ["Industry"]
