from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import campaign_service
from app.services.campaign_service import CampaignService, _featured, _paragraphs
from app.services.segment_service import _condition


def _product(**overrides):
    values = dict(
        name="Solar geyser 200L",
        description="Installed",
        image_url=None,
        unit_price=Decimal("18500.00"),
        special_price=None,
        special_until=None,
    )
    return SimpleNamespace(**(values | overrides))


def test_paragraphs_personalise_and_split():
    body = "Hi {name},\r\n\r\nNew stock is in.\nCome see us.\n\n\n"
    assert _paragraphs(body, "Thandi") == [["Hi Thandi,"], ["New stock is in.", "Come see us."]]


def test_special_price_runs_until_its_end_date():
    today = date(2026, 10, 8)
    running = _featured(_product(special_price=Decimal("15999"), special_until=today), today)
    expired = _featured(_product(special_price=Decimal("15999"), special_until=today - timedelta(days=1)), today)
    open_ended = _featured(_product(special_price=Decimal("15999")), today)
    plain = _featured(_product(), today)
    assert running["on_special"] and open_ended["on_special"]
    assert not expired["on_special"] and not plain["on_special"]


def test_unknown_rule_kind_is_rejected():
    with pytest.raises(ValueError):
        _condition({"kind": "favourite_colour"})


@pytest.mark.asyncio
async def test_compose_includes_tracking_and_unsubscribe(monkeypatch):
    company = SimpleNamespace(
        company_name="Zintos Trading", address=None, tax_number=None, logo_url=None, default_currency="ZAR"
    )

    class _Repo:
        def __init__(self, db):
            pass

        async def get_for(self, company_id):
            return company

    monkeypatch.setattr(campaign_service, "CompanySettingsRepository", _Repo)
    service = CampaignService(db=None)

    async def products(ids):
        return [_product(special_price=Decimal("15999.00"))]

    monkeypatch.setattr(service, "_products", products)
    campaign = SimpleNamespace(
        company_id="c1", name="Spring", subject="Spring specials", preheader="Up to 15% off", body="Hi {name},\n\nBig savings.",
        product_ids=["x"], cta_text="Shop now", cta_url="https://example.com/shop",
    )

    email = await service.compose(campaign, "thandi@example.com", "Thandi <b>", token="tok123")

    assert email.subject == "Spring specials"
    assert "Hi Thandi &lt;b&gt;," in email.html  # recipient names are escaped
    assert "/public/m/u/tok123" in email.html and "/public/m/o/tok123.gif" in email.html
    assert "ZAR 15,999.00" in email.html and "ZAR 18,500.00" in email.html
    assert "Unsubscribe: " in email.text and "Shop now: https://example.com/shop" in email.text
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email.headers["List-Unsubscribe"].endswith("/public/m/u/tok123>")


@pytest.mark.asyncio
async def test_preview_is_not_tracked(monkeypatch):
    company = SimpleNamespace(company_name="Z", address=None, tax_number=None, logo_url=None, default_currency="ZAR")

    class _Repo:
        def __init__(self, db):
            pass

        async def get_for(self, company_id):
            return company

    monkeypatch.setattr(campaign_service, "CompanySettingsRepository", _Repo)
    service = CampaignService(db=None)
    campaign = SimpleNamespace(company_id="c1", name="N", subject="", preheader=None, body="Hello", product_ids=[], cta_text=None, cta_url=None)
    email = await service.compose(campaign, "me@example.com", "Me", token=None)
    assert email.subject == "N"  # falls back to the campaign name
    assert ".gif" not in email.html


@pytest.mark.asyncio
async def test_name_in_the_subject_and_preview_text_is_each_recipients(monkeypatch):
    company = SimpleNamespace(company_name="Z", address=None, tax_number=None, logo_url=None, default_currency="ZAR")

    class _Repo:
        def __init__(self, db):
            pass

        async def get_for(self, company_id):
            return company

    monkeypatch.setattr(campaign_service, "CompanySettingsRepository", _Repo)
    service = CampaignService(db=None)
    campaign = SimpleNamespace(company_id="c1", name="Offer", subject="{name}, 20% off until Friday", preheader="Just for you, {name}",
                               body="Hi {name},", product_ids=[], cta_text=None, cta_url=None)
    email = await service.compose(campaign, "thandi@example.com", "Thandi", token="tok")
    assert email.subject == "Thandi, 20% off until Friday"
    assert "Just for you, Thandi" in email.html and "{name}" not in email.html
