"""Customer emails carry their document as a PDF: the invoice, quote,
purchase order, payment receipt (with the invoice), reminder and
statement. If a PDF can't be made the email still goes."""
import base64
from email import message_from_bytes

import pytest

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.services import document_service, email_service
from app.services.email_settings import EffectiveEmailConfig
from app.services.notification_service import NotificationService

from .conftest import new_company

ITEMS = [{"description": "Catering", "quantity": "2", "unit_price": "500", "tax_rate": "15"}]


def _weasyprint_works() -> bool:
    try:
        from weasyprint import HTML

        return bool(HTML(string="<p>x</p>").write_pdf())
    except Exception:
        return False


async def _invoice(api, owner) -> dict:
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Naledi Events", "email": "naledi@example.com"}, headers=h)).json()
    res = await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-10-01", "items": ITEMS}, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_the_invoice_email_carries_the_invoice(api, monkeypatch):
    monkeypatch.setattr(document_service, "pdf_from_html", lambda html: b"%PDF-1.7 fake")
    owner = await new_company(api, "Attach Co")
    invoice = await _invoice(api, owner)
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_invoice_sent(invoice["id"])
    [attachment] = email.attachments
    assert attachment["filename"] == f"Invoice {invoice['invoice_number']}.pdf"
    assert attachment["mime"] == "application/pdf" and base64.b64decode(attachment["content"]).startswith(b"%PDF")

    # And it really goes out as an attachment.
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def starttls(self, **k): ...
        def login(self, *a): ...
        def send_message(self, message): sent.append(message.as_bytes())

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    config = EffectiveEmailConfig(host="smtp.example.com", port=587, username=None, password=None, use_tls=False, from_email="ygt@example.com", from_name="Attach Co")
    email_service.send_email(config, email)
    parsed = message_from_bytes(sent[0])
    files = [(part.get_filename(), part.get_content_type()) for part in parsed.walk() if part.get_filename()]
    assert files == [(f"Invoice {invoice['invoice_number']}.pdf", "application/pdf")]


@pytest.mark.asyncio
async def test_no_pdf_still_sends_the_email(api, monkeypatch):
    monkeypatch.setattr(document_service, "pdf_from_html", lambda html: None)
    owner = await new_company(api, "No PDF Co")
    invoice = await _invoice(api, owner)
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_invoice_sent(invoice["id"])
    assert email is not None and email.attachments == []


@pytest.mark.asyncio
@pytest.mark.skipif(not _weasyprint_works(), reason="needs the Pango libraries (present in CI and on the server)")
async def test_a_real_pdf_is_made(api):
    owner = await new_company(api, "Real PDF Co")
    invoice = await _invoice(api, owner)
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        email = await NotificationService(db).compose_invoice_sent(invoice["id"])
    data = base64.b64decode(email.attachments[0]["content"])
    assert data.startswith(b"%PDF") and len(data) > 1000
