"""Client statements and printable documents."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.enums import PaymentMethod
from app.schemas.documents import DocumentTemplate
from app.services.document_service import _sample, build_statement, render

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
CUSTOMER = SimpleNamespace(id=uuid.uuid4(), name="Blue Crane Logistics", email="ap@bluecrane.test", billing_address="1 Dock Road", tax_number="4999888777")


def inv(id_, number, issued, due, total):
    return SimpleNamespace(id=id_, invoice_number=number, issue_date=issued, due_date=due, total=Decimal(total))


def pay(invoice_id, when, amount, ref=None):
    return SimpleNamespace(invoice_id=invoice_id, paid_at=when, amount=Decimal(amount), method=PaymentMethod.EFT, reference=ref)


INVOICES = [
    inv(A, "INV-0001", date(2026, 6, 1), date(2026, 7, 1), "1000.00"),
    inv(B, "INV-0002", date(2026, 8, 10), date(2026, 9, 9), "2000.00"),
    inv(C, "INV-0003", date(2026, 9, 20), date(2026, 10, 20), "500.00"),
]
PAYMENTS = [
    pay(A, datetime(2026, 6, 20, 10, tzinfo=timezone.utc), "1000.00", "BC-1"),
    pay(B, datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc), "500.00"),  # 2 Sept in Johannesburg
]


def test_opening_lines_running_balance_and_closing():
    s = build_statement(CUSTOMER, INVOICES, PAYMENTS, date(2026, 8, 1), date(2026, 9, 30), "Africa/Johannesburg")
    assert s.opening_balance == 0  # INV-0001 invoiced and paid before the period
    assert [(l.date, l.reference, l.debit, l.credit, l.balance) for l in s.lines] == [
        (date(2026, 8, 10), "INV-0002", 2000.0, 0, 2000.0),
        (date(2026, 9, 2), "INV-0002", 0, 500.0, 1500.0),  # payment dated in the company's time zone
        (date(2026, 9, 20), "INV-0003", 500.0, 0, 2000.0),
    ]
    assert (s.invoiced, s.paid, s.closing_balance) == (2500.0, 500.0, 2000.0)
    # INV-0002 is 21 days late on 30 Sept; INV-0003 isn't due yet.
    assert (s.ageing.current, s.ageing.days_30, s.ageing.days_60) == (500.0, 1500.0, 0.0)


def test_opening_balance_carries_earlier_unpaid_invoices():
    s = build_statement(CUSTOMER, INVOICES, PAYMENTS, date(2026, 9, 15), date(2026, 12, 31), "Africa/Johannesburg")
    assert s.opening_balance == 1500.0
    assert s.closing_balance == 2000.0
    # On 31 Dec INV-0002 is 113 days overdue, INV-0003 72 days.
    assert (s.ageing.days_90, s.ageing.days_120) == (500.0, 1500.0)


def _company():
    return SimpleNamespace(
        company_name="Zintos Trading (Pty) Ltd", address="5 Long Street\nCape Town", tax_number="4555000111", logo_url=None,
        sender_email="billing@zintos.test", default_currency="ZAR", default_timezone="Africa/Johannesburg",
        invoice_prefix="INV-", quote_prefix="QUO-", payment_terms_days=30,
    )


def test_documents_show_both_vat_numbers_and_the_template_choices():
    company = _company()
    customer, doc, statement = _sample(company)
    template = DocumentTemplate(layout="classic", accent="#0f766e", bank_name="FNB", account_number="62000000001", branch_code="250655",
                                invoice_terms="Payment within 30 days.", registration_number="2019/123456/07")
    invoice = render("invoice", company, template, doc=doc, customer=customer, amount_due=doc.total)
    assert "Tax invoice" in invoice and "layout-classic" in invoice and "#0f766e" in invoice
    assert "VAT number:</span> 4555000111" in invoice  # the company's
    assert f"VAT number:</span> {customer.tax_number}" in invoice  # the client's
    assert "62000000001" in invoice and "250655" in invoice and "Payment within 30 days." in invoice
    assert "Reg. no.:</span> 2019/123456/07" in invoice
    quote = render("quote", company, template.model_copy(update={"quote_title": "Estimate"}), doc=doc, customer=customer)
    assert "Estimate" in quote and "QUO-0017" in quote and "Banking details" not in quote
    page = render("statement", company, template, customer=customer, statement=statement)
    assert "Opening balance" in page and "Amount due" in page and "90+ days" in page


def test_client_vat_number_can_be_hidden_and_text_is_escaped():
    company = _company()
    customer, doc, _ = _sample(company)
    customer.name = "<b>Evil</b>"
    html = render("invoice", company, DocumentTemplate(show_customer_tax_number=False, tax_label="Tax number"), doc=doc, customer=customer, amount_due=doc.total)
    assert "&lt;b&gt;Evil&lt;/b&gt;" in html
    assert "Tax number:</span> 4555000111" in html  # the company's, with the chosen label
    assert customer.tax_number not in html  # the client's is hidden
