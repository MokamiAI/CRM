"""Email signatures: stored tidy, shown line by line, escaped, and falling
back to the company name when there isn't one."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.email_service import clean_signature, render_email
from app.services.notification_service import NotificationService


def _company(signature=None):
    return SimpleNamespace(
        company_name="Acme Ltd", address=None, tax_number=None, logo_url=None, default_currency="ZAR", email_signature=signature, document_template={}
    )


def _quote_email(company):
    quote = SimpleNamespace(
        quote_number="QUO-0003",
        issue_date=date(2026, 10, 1),
        expiry_date=date(2026, 10, 31),
        subtotal=Decimal("100.00"),
        tax_total=Decimal("15.00"),
        total=Decimal("115.00"),
        notes=None,
        po_number=None,
        items=[],
    )
    return render_email(
        "quote_sent", to="jane@customer.test", subject="Quote", customer=SimpleNamespace(name="Jane", tax_number=None), quote=quote,
        **NotificationService(db=None)._base_context(company),
    )


def test_clean_signature():
    assert clean_signature("  \r\nThabo Mokoena  \r\nSales lead\r\n\r\n") == "Thabo Mokoena\nSales lead"
    assert clean_signature("Thabo\r\n082 555 0101\n") == "Thabo\n082 555 0101"
    assert clean_signature("   \n  ") is None
    assert clean_signature(None) is None


def test_documents_without_a_signature_sign_off_with_the_company():
    email = _quote_email(_company())
    assert "Kind regards,<br>Acme Ltd" in email.html
    assert "Kind regards,\nAcme Ltd" in email.text


def test_documents_use_the_company_signature_line_by_line_and_escaped():
    email = _quote_email(_company("The Acme team\n021 555 0100 <sales@acme.test>"))
    assert "Kind regards,<br>The Acme team<br>021 555 0100 &lt;sales@acme.test&gt;" in email.html
    assert "Kind regards,\nThe Acme team\n021 555 0100 <sales@acme.test>" in email.text


def test_conversation_email_uses_the_given_signature_or_name_and_company():
    company = _company()
    base = dict(to="jane@customer.test", subject="Hello", paragraphs=[["Hi Jane"]], author_name="Thabo Mokoena", company=company)
    signed = render_email("conversation_message", signature="Thabo Mokoena\nSales lead | Acme", **base)
    assert "Thabo Mokoena<br>Sales lead | Acme" in signed.html
    assert "Thabo Mokoena\nSales lead | Acme" in signed.text
    plain = render_email("conversation_message", signature=None, **base)
    assert "Thabo Mokoena<br>Acme Ltd" in plain.html
    assert "Thabo Mokoena\nAcme Ltd" in plain.text
