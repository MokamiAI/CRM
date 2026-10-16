"""Printable invoices, quotes and statements, styled by the company's
document template (Settings > Documents). People print them, or save
them as PDF, from the browser's print dialog."""
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.enums import InvoiceStatus, PaymentMethod
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.purchasing import Supplier
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.quote_repository import QuoteRepository
from app.schemas.documents import Ageing, DocumentTemplate, StatementLine, StatementOut, resolve_template

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates" / "documents"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Invoices that count towards what a client owes.
_BILLED = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.OVERDUE)
_METHOD = {
    PaymentMethod.EFT: "EFT",
    PaymentMethod.CARD: "Card",
    PaymentMethod.CASH: "Cash",
    PaymentMethod.BANK_TRANSFER: "Bank transfer",
    PaymentMethod.OTHER: "Payment",
}

logger = logging.getLogger(__name__)


def money_formatter(currency: str):
    def money(amount) -> str:
        return f"{currency} {Decimal(str(amount)):,.2f}"

    return money


def quantity(value) -> str:
    return f"{Decimal(str(value)).normalize():f}"


def pdf_from_html(html: str) -> bytes | None:
    """The page as a PDF (WeasyPrint). None where it can't be made, e.g. a
    machine without the Pango libraries: the email then goes without it."""
    try:
        from weasyprint import HTML

        return HTML(string=html, base_url=settings.FRONTEND_URL).write_pdf()
    except Exception:
        logger.warning("Could not make a PDF", exc_info=True)
        return None


async def pdf_attachment(html: str, filename: str) -> dict[str, str] | None:
    """A PDF of the document, ready to attach to an email (or None)."""
    import asyncio
    import base64

    data = await asyncio.to_thread(pdf_from_html, html)
    if not data:
        return None
    safe = "".join(ch if ch.isalnum() or ch in " -_." else "-" for ch in filename).strip() or "document"
    return {"filename": f"{safe}.pdf", "content": base64.b64encode(data).decode(), "mime": "application/pdf"}


def render(kind: str, company, template: DocumentTemplate, **context) -> str:
    return _env.get_template(f"{kind}.html").render(
        company=company,
        t=template,
        money=money_formatter(company.default_currency),
        quantity=quantity,
        tax_short="VAT" if "vat" in template.tax_label.lower() else "Tax",
        **context,
    )


def build_statement(customer, invoices, payments, start: date, end: date, tz: str) -> StatementOut:
    """A client's account between two dates: what was owed going in, every
    invoice and payment in the period with a running balance, what's owed
    at the end, and how overdue that is. Drafts and void invoices don't count."""
    zone = ZoneInfo(tz)
    paid_on = lambda p: p.paid_at.astimezone(zone).date() if isinstance(p.paid_at, datetime) else p.paid_at  # noqa: E731
    opening = sum((Decimal(str(i.total)) for i in invoices if i.issue_date < start), Decimal(0))
    opening -= sum((Decimal(str(p.amount)) for p in payments if paid_on(p) < start), Decimal(0))

    entries = [(i.issue_date, 0, "invoice", i) for i in invoices if start <= i.issue_date <= end]
    entries += [(paid_on(p), 1, "payment", p) for p in payments if start <= paid_on(p) <= end]
    entries.sort(key=lambda e: (e[0], e[1]))

    number_of = {i.id: i.invoice_number for i in invoices}
    balance, invoiced, paid, lines = opening, Decimal(0), Decimal(0), []
    for day, _, kind, row in entries:
        if kind == "invoice":
            amount = Decimal(str(row.total))
            balance += amount
            invoiced += amount
            lines.append(StatementLine(date=day, kind=kind, reference=row.invoice_number, description="Invoice", debit=float(amount), balance=float(balance)))
        else:
            amount = Decimal(str(row.amount))
            balance -= amount
            paid += amount
            what = _METHOD.get(row.method, "Payment")
            ref = f" · {row.reference}" if row.reference else ""
            lines.append(
                StatementLine(
                    date=day, kind=kind, reference=number_of.get(row.invoice_id, ""), description=f"{what}{ref}", credit=float(amount), balance=float(balance)
                )
            )

    # Ageing: what's still unpaid on each invoice at the end date, by days overdue.
    paid_by_invoice: dict[uuid.UUID, Decimal] = {}
    for p in payments:
        if paid_on(p) <= end:
            paid_by_invoice[p.invoice_id] = paid_by_invoice.get(p.invoice_id, Decimal(0)) + Decimal(str(p.amount))
    buckets = {"current": Decimal(0), "days_30": Decimal(0), "days_60": Decimal(0), "days_90": Decimal(0), "days_120": Decimal(0)}
    for inv in invoices:
        if inv.issue_date > end:
            continue
        outstanding = Decimal(str(inv.total)) - paid_by_invoice.get(inv.id, Decimal(0))
        if outstanding <= 0:
            continue
        late = (end - inv.due_date).days
        key = "current" if late <= 0 else "days_30" if late <= 30 else "days_60" if late <= 60 else "days_90" if late <= 90 else "days_120"
        buckets[key] += outstanding

    return StatementOut(
        customer_id=str(customer.id),
        customer_name=customer.name,
        start=start,
        end=end,
        opening_balance=float(opening),
        invoiced=float(invoiced),
        paid=float(paid),
        closing_balance=float(balance),
        lines=lines,
        ageing=Ageing(**{k: float(v) for k, v in buckets.items()}),
    )


def supplier_party(supplier):
    """A supplier in the shape the documents' address block expects."""
    return SimpleNamespace(name=supplier.name, billing_address=supplier.address, email=supplier.email, phone=supplier.phone, tax_number=supplier.tax_number)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.companies = CompanySettingsRepository(db)

    async def _company(self):
        company = await self.companies.get_current()
        return company, resolve_template(company)

    async def _people(self, customer_id):
        """The customer's main contact, printed as "Attention". (Who made
        the document shows in the app, not on the printout.)"""
        from app.models.crm import Contact

        contact = await self.db.scalar(
            select(Contact).where(Contact.customer_id == customer_id).order_by(Contact.is_primary.desc(), Contact.created_at).limit(1)
        )
        return {"contact": contact}

    async def invoice_html(self, invoice_id: uuid.UUID) -> str:
        invoice = await InvoiceRepository(self.db).get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        customer = await CustomerRepository(self.db).get_by_id(invoice.customer_id)
        company, template = await self._company()
        people = await self._people(invoice.customer_id)
        return render("invoice", company, template, doc=invoice, customer=customer, amount_due=invoice.total - invoice.amount_paid, **people)

    async def quote_html(self, quote_id: uuid.UUID) -> str:
        quote = await QuoteRepository(self.db).get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        customer = await CustomerRepository(self.db).get_by_id(quote.customer_id)
        company, template = await self._company()
        people = await self._people(quote.customer_id)
        return render("quote", company, template, doc=quote, customer=customer, **people)

    async def purchase_order_html(self, po_id: uuid.UUID) -> str:
        from app.services.purchasing_service import PurchaseOrderService

        po = await PurchaseOrderService(self.db).get(po_id)
        supplier = await self.db.get(Supplier, po.supplier_id)
        company, template = await self._company()
        # The supplier's contact person prints as "Attention", like a customer's.
        contact = SimpleNamespace(first_name=supplier.contact_name, last_name=None, job_title=None, email=None, phone=None) if supplier.contact_name else None
        return render("purchase_order", company, template, doc=po, customer=supplier_party(supplier), contact=contact)

    async def statement(self, customer_id: uuid.UUID, start: date, end: date):
        customer = await CustomerRepository(self.db).get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
        invoices = list(
            await self.db.scalars(select(Invoice).where(Invoice.customer_id == customer_id, Invoice.status.in_(_BILLED)).order_by(Invoice.issue_date))
        )
        payments = list(
            await self.db.scalars(
                select(Payment).join(Invoice, Payment.invoice_id == Invoice.id).where(Invoice.customer_id == customer_id, Invoice.status.in_(_BILLED))
            )
        )
        company, template = await self._company()
        return customer, company, template, build_statement(customer, invoices, payments, start, end, company.default_timezone)

    async def statement_html(self, customer_id: uuid.UUID, start: date, end: date) -> str:
        customer, company, template, statement = await self.statement(customer_id, start, end)
        return render("statement", company, template, customer=customer, statement=statement)

    async def preview_html(self, template: DocumentTemplate, kind: str) -> str:
        """Settings > Documents: the template applied to made-up records."""
        company, _ = await self._company()
        customer, doc, statement = _sample(company)
        if kind == "statement":
            return render("statement", company, template, customer=customer, statement=statement)
        sample_people = {
            "contact": SimpleNamespace(first_name="Lindiwe", last_name="Khoza", email="lindiwe@thandeka.example.com", phone="011 555 0142", job_title="Finance manager"),
        }
        return render(kind, company, template, doc=doc, customer=customer, amount_due=doc.total, **sample_people)


def _sample(company):
    today = date.today()
    customer = SimpleNamespace(
        id=uuid.uuid4(), name="Thandeka Holdings (Pty) Ltd", email="accounts@thandeka.example.com",
        billing_address="12 Loop Street\nCape Town\n8001", tax_number="4123456789",
        delivery_address="Unit 4, Rosebank Office Park\n15 Tyrwhitt Avenue\nRosebank, Johannesburg\n2196", phone="011 555 0140",
    )
    items = [
        SimpleNamespace(description="Website design and build", quantity=Decimal("1"), unit_price=Decimal("18500.00"), tax_rate=Decimal("15"), line_total=Decimal("18500.00")),
        SimpleNamespace(description="Monthly hosting and support", quantity=Decimal("3"), unit_price=Decimal("650.00"), tax_rate=Decimal("15"), line_total=Decimal("1950.00")),
    ]
    subtotal = Decimal("20450.00")
    tax = Decimal("3067.50")
    doc = SimpleNamespace(
        invoice_number=f"{company.invoice_prefix}0042", quote_number=f"{company.quote_prefix}0017",
        issue_date=today, due_date=today + timedelta(days=company.payment_terms_days or 30), expiry_date=today + timedelta(days=30),
        subtotal=subtotal, tax_total=tax, total=subtotal + tax, amount_paid=Decimal("0"), notes="Thank you for your business.", items=items, po_number="PO-7781", reference="Rosebank office fit-out",
        title="Rosebank office fit-out: website and support", description="A new website for the Rosebank office, with three months of hosting and support after launch.",
    )
    inv = lambda n, d, total, due: SimpleNamespace(id=n, invoice_number=f"{company.invoice_prefix}00{n}", issue_date=today - timedelta(days=d), due_date=today - timedelta(days=d - 30), total=Decimal(total))  # noqa: E731
    invoices = [inv(38, 75, "8625.00", 0), inv(40, 40, "4312.50", 0), inv(42, 5, "23517.50", 0)]
    pay = lambda n, d, amount, ref: SimpleNamespace(invoice_id=n, paid_at=today - timedelta(days=d), amount=Decimal(amount), method=PaymentMethod.EFT, reference=ref)  # noqa: E731
    payments = [pay(38, 60, "8625.00", "THANDEKA38"), pay(40, 10, "2000.00", "THANDEKA40")]
    statement = build_statement(customer, invoices, payments, today - timedelta(days=90), today, company.default_timezone)
    return customer, doc, statement
