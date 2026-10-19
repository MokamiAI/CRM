"""Expired trials receive one unpaid invoice, with manual confirmation."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, update
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ConflictError
from app.core.tenancy import set_system
from app.core.plans import PLANS
from app.models.billing import BillingPayment, Subscription, SubscriptionInvoice
from app.models.user import User
from app.services.manual_billing import issue_trial_invoice, invoice_email
from app.services.subscription_invoices import save_details, render_html
from app.tasks import billing_tasks
from .conftest import new_company

DETAILS = {"legal_name": "Example Test Company", "address": "1 Example Road", "registration_number": "TEST-123",
    "email": "billing@example.com", "bank_name": "Test Bank", "account_holder": "Example Test Company",
    "account_number": "123456789", "branch_code": "000001"}


async def setup(api, expired=True):
    owner = await new_company(api, "Manual Billing Co")
    async with AsyncSessionLocal() as db:
        set_system(db)
        await save_details(db, DETAILS)
        sub = await db.scalar(select(Subscription).where(Subscription.company_id == owner["company_id"]))
        sub.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=-1 if expired else 15)
        sid = sub.id
        await db.commit()
    return owner, sid


@pytest.mark.asyncio
async def test_expiry_invoice_is_unpaid_unique_and_preserves_tenancy(api):
    owner, sid = await setup(api)
    async with AsyncSessionLocal() as db:
        set_system(db)
        invoice = await issue_trial_invoice(db, sid)
        assert not invoice.is_paid and invoice.payment_id is None
        assert invoice.seats == 1  # not the ten-seat trial allowance
        assert invoice.amount_cents == PLANS["grow"].price_cents("monthly", 1)
        assert invoice_email(invoice, owner["email"]).to == owner["email"]
        html = render_html(invoice)
        assert "Unpaid" in html and "Test Bank" in html and "123456789" in html
        assert "Paid in full" not in html and "Paystack" not in html
        iid = invoice.id
        await db.commit()
        assert await issue_trial_invoice(db, sid) is None
    other = await new_company(api, "Other Manual Co")
    assert (await api.get(f"/billing/invoices/{iid}/document", headers=other["headers"])).status_code == 404
    listing = (await api.get("/billing/invoices", headers=owner["headers"])).json()
    assert len(listing) == 1 and listing[0]["is_paid"] is False


@pytest.mark.asyncio
async def test_unexpired_trial_and_missing_details_do_not_issue(api):
    owner, sid = await setup(api, expired=False)
    async with AsyncSessionLocal() as db:
        set_system(db)
        assert await issue_trial_invoice(db, sid) is None
        await db.execute(update(Subscription).where(Subscription.id == sid).values(trial_ends_at=datetime.now(timezone.utc)-timedelta(days=1)))
        await save_details(db, {"legal_name": "YGT"})
        with pytest.raises(ConflictError):
            await issue_trial_invoice(db, sid)
        await db.rollback()


@pytest.mark.asyncio
async def test_trial_invoice_delivery_retries_and_does_not_resend(api, monkeypatch):
    owner, sid = await setup(api)
    async with AsyncSessionLocal() as db:
        set_system(db)
        invoice = await issue_trial_invoice(db, sid)
        iid = invoice.id
        await db.commit()
    async def pdf(*args):
        return {"filename": "invoice.pdf", "content": "JVBERg==", "mime": "application/pdf"}
    monkeypatch.setattr(billing_tasks, "pdf_attachment", pdf)
    def fail(*args):
        raise OSError("SMTP unavailable")
    monkeypatch.setattr(billing_tasks, "send_email", fail)
    with pytest.raises(OSError):
        await billing_tasks.deliver_invoice(iid)
    sent = []
    monkeypatch.setattr(billing_tasks, "send_email", lambda config, email: sent.append(email))
    assert await billing_tasks.deliver_invoice(iid)
    assert len(sent) == 1 and sent[0].attachments[0]["mime"] == "application/pdf"
    assert "payment due" in sent[0].subject and "123456789" in sent[0].text
    assert await billing_tasks.deliver_invoice(iid) is False
    assert len(sent) == 1
    monkeypatch.setattr(settings, "MANUAL_TRIAL_INVOICES_ENABLED", False)
    assert await billing_tasks.invoice_expired_trials() == 0


@pytest.mark.asyncio
async def test_only_platform_admin_can_confirm_actual_payment_once(api, monkeypatch):
    owner, sid = await setup(api)
    async with AsyncSessionLocal() as db:
        set_system(db)
        invoice = await issue_trial_invoice(db, sid)
        iid, number = invoice.id, invoice.number
        await db.execute(update(User).where(User.id == owner["user_id"]).values(email_verified_at=datetime.now(timezone.utc)))
        await db.commit()
    url = f"/admin/subscription-invoices/{iid}/confirm-payment"
    assert (await api.post(url, headers=owner["headers"])).status_code == 403
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", owner["email"])
    assert (await api.post(url, headers=owner["headers"])).status_code == 200
    assert (await api.post(url, headers=owner["headers"])).status_code == 200
    async with AsyncSessionLocal() as db:
        set_system(db)
        invoice = await db.get(SubscriptionInvoice, iid)
        assert invoice.is_paid and invoice.number == number
        sub = await db.get(Subscription, sid)
        assert sub.status == "active" and sub.current_period_end > datetime.now(timezone.utc)
        payments = list(await db.scalars(select(BillingPayment).where(BillingPayment.company_id == owner["company_id"])))
        assert len(payments) == 1 and payments[0].amount_cents == invoice.amount_cents
