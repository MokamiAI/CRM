from types import SimpleNamespace

import pytest

from app.services.custom_field_service import CustomFieldError, CustomFieldService, _slug


def _field(key, field_type, required=False, options=()):
    return SimpleNamespace(key=key, label=key.title(), field_type=field_type, required=required, options=list(options))


@pytest.fixture
def service(monkeypatch):
    fields = [
        _field("industry", "select", options=["Retail", "Mining"]),
        _field("staff", "number"),
        _field("since", "date"),
        _field("vip", "boolean"),
        _field("branch", "text"),
    ]

    async def list_fields(self, entity=None):
        return fields

    monkeypatch.setattr(CustomFieldService, "list_fields", list_fields)
    svc = CustomFieldService(db=None)
    svc.fields = fields
    return svc


@pytest.mark.asyncio
async def test_coerces_each_type(service):
    values = await service.clean_values(
        "customer",
        {"industry": "Mining", "staff": "1 200", "since": "2024-03-01", "vip": "yes", "branch": "  Durban "},
    )
    assert values == {"industry": "Mining", "staff": 1200, "since": "2024-03-01", "vip": True, "branch": "Durban"}


@pytest.mark.asyncio
async def test_decimal_comma_number(service):
    assert (await service.clean_values("customer", {"staff": "2,5"}))["staff"] == 2.5


@pytest.mark.asyncio
async def test_blank_clears_and_merges_with_current(service):
    values = await service.clean_values("customer", {"branch": "", "vip": False}, current={"branch": "Durban", "staff": 3})
    assert values == {"staff": 3, "vip": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [{"industry": "Farming"}, {"staff": "many"}, {"since": "31/02/2024"}, {"vip": "maybe"}, {"nope": "x"}],
)
async def test_rejects_invalid(service, values):
    with pytest.raises(CustomFieldError):
        await service.clean_values("customer", values)


@pytest.mark.asyncio
async def test_required_field(service):
    service.fields[4].required = True
    with pytest.raises(CustomFieldError, match="Branch"):
        await service.clean_values("customer", {"vip": True})
    assert await service.clean_values("customer", {}, current={"branch": "Durban"}) == {"branch": "Durban"}


def test_slug():
    assert _slug("ID / Passport no.") == "id_passport_no"
    assert _slug("!!!") == "field"
