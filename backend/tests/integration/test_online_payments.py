"""Customers paying invoices online, into the company's own Paystack account:
only what is still owed is ever charged, a payment is recorded once however
many times it is confirmed, and links, keys and webhooks can't be forged."""
import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.models.notification import Notification
from app.models.payment import OnlinePayment, Payment
from app.services import channel_providers as providers
from app.services.online_payment_service import check_pending, invoice_id_from, pay_token

from .conftest import new_company

KEY = "sk_test_ygt_online_payments"


class FakePaystack:
    """Stands in for Paystack: remembers each checkout, and says each was
    paid in full by card unless a test says otherwise."""

    def __init__(self, monkeypatch):
        self.started: list[dict] = []
        self.outcome: dict[str, dict] = {}
        self.verified = 0

        async def start(secrets, **kwargs):
            assert secrets["secret_key"] == KEY
            self.started.append(kwargs)
            return f"https://checkout.paystack.test/{kwargs['reference']}"

        async def verify(secrets, reference):
            self.verified += 1
            started = next(s for s in self.started if s["reference"] == reference)
            return self.outcome.get(
                reference,
                {"status": "success", "reference": reference, "amount": started["amount_cents"], "currency": started["currency"], "channel": "card", "paid_at": "2026-11-20T08:00:00.000Z"},
            )

        async def balance(method, path, secrets, **kwargs):
            providers._paystack_key(secrets)
            return [{"currency": "ZAR", "balance": 0}]

        monkeypatch.setattr(providers, "paystack_start", start)
        monkeypatch.setattr(providers, "paystack_verify", verify)
        monkeypatch.setattr(providers, "_paystack", balance)

    @property
    def last(self) -> dict:
        return self.started[-1]


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


async def _connect(api, headers, key: str = KEY):
    res = await api.put("/settings/channels/payments", json={"provider": "paystack", "enabled": True, "secrets": {"secret_key": key}}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _sent_invoice(api, headers, amount: str = "1150.00", email: str | None = "client@example.com") -> dict:
    customer = (await api.post("/customers", json={"name": "Sizwe Client", **({"email": email} if email else {})}, headers=headers)).json()
    res = await api.post(
        "/invoices",
        json={"customer_id": customer["id"], "issue_date": _day(0), "due_date": _day(14), "items": [{"description": "Tiling", "quantity": "1", "unit_price": amount, "tax_rate": "0"}]},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    invoice = res.json()
    assert (await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=headers)).status_code == 200
    return invoice


async def _token(api, headers, invoice_id) -> str:
    res = await api.get(f"/invoices/{invoice_id}/pay-link", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["url"], res.json()
    return res.json()["url"].rsplit("/", 1)[1]


async def _counts(company_id, invoice_id) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        set_tenant(db, company_id)
        payments = await db.scalar(select(func.count()).select_from(Payment).where(Payment.invoice_id == invoice_id))
        notes = await db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "online_payment"))
    return payments, notes


@pytest.mark.asyncio
async def test_a_customer_pays_online_and_it_is_recorded_once(api, monkeypatch):
    paystack = FakePaystack(monkeypatch)
    owner = await new_company(api, "Sizwe Builders")
    h = owner["headers"]
    conn = await _connect(api, h)
    assert conn["webhook_url"].endswith("/payments")
    invoice = await _sent_invoice(api, h)
    token = await _token(api, h, invoice["id"])

    page = await api.get(f"/public/pay/{token}")
    assert page.status_code == 200 and "Pay ZAR 1,150.00" in page.text and "Sizwe Builders" in page.text
    assert not paystack.started  # opening the link (or a mail scanner) starts nothing

    res = await api.post(f"/public/pay/{token}")
    assert res.status_code == 303 and res.headers["location"].startswith("https://checkout.paystack.test/")
    assert paystack.last["amount_cents"] == 115000 and paystack.last["currency"] == "ZAR" and paystack.last["email"] == "client@example.com"
    assert paystack.last["callback_url"].endswith(f"/public/pay/{token}/done")
    reference = paystack.last["reference"]

    done = await api.get(f"/public/pay/{token}/done", params={"reference": reference})
    assert done.status_code == 200 and "your payment went through" in done.text
    detail = (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()
    assert detail["status"] == "paid" and Decimal(detail["amount_paid"]) == Decimal("1150.00")
    payments = (await api.get(f"/invoices/{invoice['id']}/payments", headers=h)).json()
    assert len(payments) == 1 and payments[0]["method"] == "card" and payments[0]["reference"] == reference
    assert ("app.tasks.email_tasks.send_payment_receipt_task", (payments[0]["id"],)) in api.queued
    assert await _counts(owner["company_id"], invoice["id"]) == (1, 1)

    # The webhook, a second return, and the periodic check all arrive too.
    body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode()
    signature = hmac.new(KEY.encode(), body, hashlib.sha512).hexdigest()
    hook_path = "/public/channels/" + conn["webhook_url"].split("/public/channels/", 1)[1]
    hook = await api.post(hook_path, content=body, headers={"x-paystack-signature": signature, "content-type": "application/json"})
    assert hook.status_code == 200
    await api.get(f"/public/pay/{token}/done", params={"reference": reference})
    await check_pending()
    assert await _counts(owner["company_id"], invoice["id"]) == (1, 1)

    # Paid: the link now says so and can't start another payment.
    again = await api.get(f"/public/pay/{token}")
    assert "is paid" in again.text
    assert (await api.get(f"/invoices/{invoice['id']}/pay-link", headers=h)).json() == {"available": True, "url": None}
    started = len(paystack.started)
    await api.post(f"/public/pay/{token}")
    assert len(paystack.started) == started


@pytest.mark.asyncio
async def test_only_what_is_still_owed_is_charged(api, monkeypatch):
    paystack = FakePaystack(monkeypatch)
    owner = await new_company(api, "Thandi Tiling")
    h = owner["headers"]
    await _connect(api, h)
    invoice = await _sent_invoice(api, h, amount="1000.00", email=None)
    assert (await api.post(f"/invoices/{invoice['id']}/payments", json={"amount": "400", "method": "eft"}, headers=h)).status_code == 201
    token = await _token(api, h, invoice["id"])

    page = await api.get(f"/public/pay/{token}")
    assert "Pay ZAR 600.00" in page.text and 'name="email"' in page.text  # no email on file: the payer gives one
    res = await api.post(f"/public/pay/{token}", data={"email": "payer@example.com"})
    assert res.status_code == 303 and paystack.last["amount_cents"] == 60000 and paystack.last["email"] == "payer@example.com"

    # The owner records the rest by EFT before the customer finishes paying.
    assert (await api.post(f"/invoices/{invoice['id']}/payments", json={"amount": "600", "method": "eft"}, headers=h)).status_code == 201
    done = await api.get(f"/public/pay/{token}/done", params={"reference": paystack.last["reference"]})
    assert done.status_code == 200
    payments, _ = await _counts(owner["company_id"], invoice["id"])
    assert payments == 2  # the two EFTs: the online one is not added on top
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        attempt = await db.scalar(select(OnlinePayment).where(OnlinePayment.reference == paystack.last["reference"]))
        assert attempt.status == "needs_attention"
        note = await db.scalar(select(Notification).where(Notification.kind == "online_payment"))
        assert note is not None and "Check an online payment" in note.title


@pytest.mark.asyncio
async def test_an_unfinished_checkout_waits_then_a_failed_one_takes_nothing(api, monkeypatch):
    paystack = FakePaystack(monkeypatch)
    owner = await new_company(api, "Pending Plumbing")
    h = owner["headers"]
    await _connect(api, h)
    invoice = await _sent_invoice(api, h)
    token = await _token(api, h, invoice["id"])
    await api.post(f"/public/pay/{token}")
    reference = paystack.last["reference"]

    paystack.outcome[reference] = {"status": "abandoned", "reference": reference}
    waiting = await api.get(f"/public/pay/{token}/done", params={"reference": reference})
    assert "Waiting for Paystack" in waiting.text
    paystack.outcome[reference] = {"status": "failed", "reference": reference, "gateway_response": "Declined"}
    failed = await api.get(f"/public/pay/{token}/done", params={"reference": reference})
    assert "didn't go through" in failed.text and "Try again" in failed.text
    assert (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()["status"] == "sent"
    assert await _counts(owner["company_id"], invoice["id"]) == (0, 0)


@pytest.mark.asyncio
async def test_links_keys_and_webhooks_cannot_be_forged(api, monkeypatch):
    paystack = FakePaystack(monkeypatch)
    owner = await new_company(api, "Careful Carpentry")
    h = owner["headers"]
    invoice = await _sent_invoice(api, h)

    # Not switched on: no link, and the page points to EFT.
    assert (await api.get(f"/invoices/{invoice['id']}/pay-link", headers=h)).json() == {"available": False, "url": None}
    token = pay_token(__import__("uuid").UUID(invoice["id"]))
    assert "Online payment isn't available" in (await api.get(f"/public/pay/{token}")).text

    # A public key is refused when testing, with a clear message.
    await _connect(api, h, key="pk_test_wrong")
    tested = (await api.post("/settings/channels/payments/test", json={}, headers=h)).json()
    assert tested["status"] == "error" and "public key" in tested["last_error"]
    conn = await _connect(api, h)
    assert (await api.post("/settings/channels/payments/test", json={}, headers=h)).json()["status"] == "ok"

    # A changed link isn't ours.
    assert invoice_id_from(token) is not None
    forged = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert invoice_id_from(forged) is None
    assert "Link not recognised" in (await api.get(f"/public/pay/{forged}")).text

    # A webhook not signed with the company's key records nothing.
    await api.post(f"/public/pay/{token}")
    body = json.dumps({"event": "charge.success", "data": {"reference": paystack.last["reference"]}}).encode()
    hook_path = "/public/channels/" + conn["webhook_url"].split("/public/channels/", 1)[1]
    res = await api.post(hook_path, content=body, headers={"x-paystack-signature": "0" * 128, "content-type": "application/json"})
    assert res.json() == {"accepted": 0}
    assert paystack.verified == 0
    assert await _counts(owner["company_id"], invoice["id"]) == (0, 0)


@pytest.mark.asyncio
async def test_invoice_emails_and_pdf_carry_the_pay_link(api, monkeypatch):
    FakePaystack(monkeypatch)
    from app.services import document_service

    # The file name is what matters here; real PDFs need WeasyPrint's system libraries.
    monkeypatch.setattr(document_service, "pdf_from_html", lambda html: b"%PDF-1.7 test")
    owner = await new_company(api, "Linked Lighting")
    h = owner["headers"]
    invoice = await _sent_invoice(api, h)
    from app.services.document_service import DocumentService
    from app.services.notification_service import NotificationService

    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_invoice_sent(invoice["id"])
        assert "/public/pay/" not in email.html and "Pay online" not in await DocumentService(db).invoice_html(invoice["id"])

    await _connect(api, h)
    token = await _token(api, h, invoice["id"])
    pay_url = (await api.get(f"/invoices/{invoice['id']}/pay-link", headers=h)).json()["url"]
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_invoice_sent(invoice["id"])
        assert email.attachments[0]["filename"] == f"Sizwe Client - {invoice['invoice_number']}.pdf"
        assert f"/public/pay/{token}" in email.html and f"/public/pay/{token}" in email.text and "Pay ZAR 1,150.00 now" in email.html
        reminder = await NotificationService(db).compose_invoice_reminder(invoice["id"])
        assert f"/public/pay/{token}" in reminder.html
        html = await DocumentService(db).invoice_html(invoice["id"])
        assert "Pay online" in html and "data:image/svg+xml" in html
        # A "Pay now" button that opens the pay page, not the long address printed out.
        assert f'<a class="pay-now" href="{pay_url}">Pay now</a>' in html and f">{pay_url}<" not in html
        assert "<title>Sizwe Client - " in html


@pytest.mark.asyncio
async def test_a_declined_card_then_another_card_on_the_same_checkout_is_recorded(api, monkeypatch):
    paystack = FakePaystack(monkeypatch)
    owner = await new_company(api, "Retry Roofing")
    h = owner["headers"]
    await _connect(api, h)
    invoice = await _sent_invoice(api, h, email=None)
    token = await _token(api, h, invoice["id"])

    # A mistyped email gets a plain message, and no checkout is opened.
    page = await api.post(f"/public/pay/{token}", data={"email": "client@example"})
    assert page.status_code == 200 and "Please check your email address" in page.text and not paystack.started

    await api.post(f"/public/pay/{token}", data={"email": "client@example.com"})
    reference = paystack.last["reference"]
    paystack.outcome[reference] = {"status": "failed", "reference": reference, "gateway_response": "Declined"}
    assert "didn't go through" in (await api.get(f"/public/pay/{token}/done", params={"reference": reference})).text

    # The customer tries another card on the same Paystack page, and it works.
    del paystack.outcome[reference]
    from datetime import datetime, timedelta, timezone

    await check_pending(now=datetime.now(timezone.utc) + timedelta(minutes=5))
    assert (await api.get(f"/invoices/{invoice['id']}", headers=h)).json()["status"] == "paid"
    assert await _counts(owner["company_id"], invoice["id"]) == (1, 1)
