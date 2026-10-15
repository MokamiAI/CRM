"""Every confirmed subscription payment gets YGT's own invoice: numbered,
tied to the Paystack reference, emailed, made once, and VAT only once YGT
has a VAT number. Companies show a VAT number only when registered."""
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.billing import PaystackPlan, SubscriptionInvoice
from app.models.platform import PlatformSetting
from app.models.user import User
from app.services.billing_service import BillingService

from .conftest import new_company


async def _pay(owner: dict, reference: str, amount: int = 44700) -> None:
    """A Paystack charge for Grow (3 people), as the webhook delivers it."""
    plan_code = f"PLN_test_{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        set_system(db)
        db.add(PaystackPlan(key=f"test:{uuid.uuid4().hex}", plan_code=plan_code, amount_cents=amount))
        await db.flush()
        set_tenant(db, owner["company_id"])
        service = BillingService(db)
        sub = await service.subscription()
        await service._apply_charge(sub, {
            "reference": reference, "amount": amount, "currency": "ZAR", "plan": plan_code,
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"company_id": str(owner["company_id"]), "plan": "grow", "interval": "monthly", "seats": 3},
            "customer": {"email": owner["email"], "customer_code": "CUS_test"},
        })
        await db.commit()


async def _ygt_admin(api, monkeypatch, owner):
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", owner["email"])
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(User).where(User.id == owner["user_id"]).values(email_verified_at=datetime.now(timezone.utc)))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def _no_ygt_vat():
    """Each test starts with YGT not registered for VAT."""
    async with AsyncSessionLocal() as db:
        set_system(db)
        row = await db.get(PlatformSetting, "ygt_details")
        if row is not None:
            await db.delete(row)
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_payment_makes_one_invoice_and_emails_it(api):
    owner = await new_company(api, "Paying Co")
    h = owner["headers"]
    reference = f"ygt_test_{uuid.uuid4().hex}"
    before = len(api.queued)
    await _pay(owner, reference)
    await _pay(owner, reference)  # the webhook and the redirect both arrive

    invoices = (await api.get("/billing/invoices", headers=h)).json()
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv["number"].startswith("YGT-INV-") and len(inv["number"]) == 14
    assert inv["payment_reference"] == reference and inv["amount_cents"] == 44700 and inv["vat_cents"] == 0
    assert inv["plan"] == "grow" and inv["seats"] == 3

    sent = [args[0] for name, args in api.queued[before:] if name.endswith("send_platform_email_task")]
    assert len(sent) == 1 and sent[0]["to"] == owner["email"] and inv["number"] in sent[0]["subject"]
    assert reference in sent[0]["text"]

    html = (await api.get(f"/billing/invoices/{inv['id']}/document", headers=h)).text
    assert inv["number"] in html and reference in html and "Paying Co" in html
    assert "Tax invoice" not in html and "not registered for VAT" in html and "Paid in full" in html

    other = (await new_company(api, "Nosy Co"))["headers"]
    assert (await api.get("/billing/invoices", headers=other)).json() == []
    assert (await api.get(f"/billing/invoices/{inv['id']}/document", headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_vat_starts_once_ygt_has_a_vat_number_and_numbers_keep_counting(api, monkeypatch):
    owner = await new_company(api, "Taxed Co")
    h = owner["headers"]
    await _pay(owner, f"ygt_test_{uuid.uuid4().hex}")
    first = (await api.get("/billing/invoices", headers=h)).json()[0]

    await _ygt_admin(api, monkeypatch, owner)
    saved = await api.put("/admin/ygt-details", json={"legal_name": "YGT (Pty) Ltd", "address": "1 Sandton Drive", "registration_number": "2026/123456/07", "vat_number": "4123456789"}, headers=h)
    assert saved.status_code == 200 and saved.json()["vat_number"] == "4123456789"

    await _pay(owner, f"ygt_test_{uuid.uuid4().hex}")
    newest = (await api.get("/billing/invoices", headers=h)).json()[0]
    assert int(newest["number"][-6:]) > int(first["number"][-6:])
    assert newest["vat_cents"] == 5830  # 447.00 incl. 15% VAT
    html = (await api.get(f"/billing/invoices/{newest['id']}/document", headers=h)).text
    assert "Tax invoice" in html and "4123456789" in html and "YGT (Pty) Ltd" in html

    # The earlier invoice keeps what it was issued with.
    old = (await api.get(f"/billing/invoices/{first['id']}/document", headers=h)).text
    assert "Tax invoice" not in old and "4123456789" not in old


@pytest.mark.asyncio
async def test_only_ygt_team_edits_ygt_details(api):
    owner = await new_company(api, "Not Staff Co")
    assert (await api.put("/admin/ygt-details", json={"legal_name": "Hacked"}, headers=owner["headers"])).status_code == 403


@pytest.mark.asyncio
async def test_company_vat_number_shows_only_when_registered(api):
    owner = await new_company(api, "Small Trader")
    h = owner["headers"]
    await api.patch("/settings", json={"tax_number": "4999999999"}, headers=h)
    customer = (await api.post("/customers", json={"name": "Client"}, headers=h)).json()
    inv = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": date.today().isoformat(), "items": [{"description": "Work", "quantity": "1", "unit_price": "100", "tax_rate": "0"}]}, headers=h)).json()
    html = (await api.get(f"/invoices/{inv['id']}/document", headers=h)).text
    assert "4999999999" not in html and "Tax invoice" not in html and "Invoice" in html

    assert (await api.patch("/settings", json={"vat_registered": True}, headers=h)).json()["vat_registered"] is True
    html = (await api.get(f"/invoices/{inv['id']}/document", headers=h)).text
    assert "4999999999" in html and "Tax invoice" in html
    assert (await api.get("/company", headers=h)).json()["vat_registered"] is True


@pytest.mark.asyncio
async def test_two_companies_paying_at_once_get_different_numbers(api, monkeypatch):
    import asyncio

    from app.services import subscription_invoices

    real_next = subscription_invoices._next_number

    async def slow_next(db):
        # Hold the numbering step open, so the payments really overlap.
        number = await real_next(db)
        await asyncio.sleep(0.3)
        return number

    monkeypatch.setattr(subscription_invoices, "_next_number", slow_next)
    a = await new_company(api, "Busy Co")
    b = await new_company(api, "Also Busy Co")
    await asyncio.gather(*(_pay(owner, f"ygt_test_{uuid.uuid4().hex}") for owner in (a, b, a, b)))
    async with AsyncSessionLocal() as db:
        set_system(db)
        numbers = (await db.scalars(select(SubscriptionInvoice.number).where(SubscriptionInvoice.company_id.in_([a["company_id"], b["company_id"]])))).all()
        assert len(numbers) == 4 and len(set(numbers)) == 4
