import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.tenancy import get_tenant, set_tenant
from app.models.company_settings import CompanySettings
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.quote_repository import QuoteRepository
from app.schemas.documents import resolve_template
from app.services.document_service import DocumentService
from app.services.email_service import OutgoingEmail, render_email
from app.services.email_settings import EffectiveEmailConfig, resolve_email_config
from app.services.reminder_service import REMINDABLE, company_today


def _money_formatter(currency: str):
    def money(amount) -> str:
        return f"{currency} {Decimal(amount):,.2f}"

    return money


def _quantity(value) -> str:
    # 2.00 -> "2", 1.50 -> "1.5": line-item quantities are mostly whole units.
    return f"{Decimal(value).normalize():f}"


class NotificationService:
    """Composes customer-facing emails from database records. Composing is
    async (it reads the DB); sending is not — callers pass the result to
    app.services.email_service.send_email, normally from a Celery task in
    app/tasks/email_tasks.py.

    compose_* methods return None when the customer has no email address,
    which is a normal state for a customer record rather than an error."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)
        self.customers = CustomerRepository(db)
        self.invoices = InvoiceRepository(db)
        self.quotes = QuoteRepository(db)
        self.payments = PaymentRepository(db)

    async def email_config(self) -> EffectiveEmailConfig:
        return resolve_email_config(await self.company_settings.get_current())

    def _adopt(self, record) -> None:
        """Background jobs start in SYSTEM mode and only know a record id;
        once the record is loaded, act as its company from then on."""
        if get_tenant(self.db) is None:
            set_tenant(self.db, record.company_id)

    def _base_context(self, company: CompanySettings) -> dict:
        return {
            "company": company,
            "signature": company.email_signature,
            "t": resolve_template(company),
            "money": _money_formatter(company.default_currency),
            "quantity": _quantity,
        }

    async def compose_invoice_sent(self, invoice_id: uuid.UUID) -> OutgoingEmail | None:
        invoice = await self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        self._adopt(invoice)
        customer = await self.customers.get_by_id(invoice.customer_id)
        if customer is None or not customer.email:
            return None
        company = await self.company_settings.get_current()
        return render_email(
            "invoice_sent",
            to=customer.email,
            subject=f"Invoice {invoice.invoice_number} from {company.company_name}",
            customer=customer,
            invoice=invoice,
            amount_due=invoice.total - invoice.amount_paid,
            **self._base_context(company),
        )

    async def compose_quote_sent(self, quote_id: uuid.UUID) -> OutgoingEmail | None:
        quote = await self.quotes.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        self._adopt(quote)
        customer = await self.customers.get_by_id(quote.customer_id)
        if customer is None or not customer.email:
            return None
        company = await self.company_settings.get_current()
        return render_email(
            "quote_sent",
            to=customer.email,
            subject=f"Quote {quote.quote_number} from {company.company_name}",
            customer=customer,
            quote=quote,
            **self._base_context(company),
        )

    async def compose_payment_receipt(self, payment_id: uuid.UUID) -> OutgoingEmail | None:
        payment = await self.payments.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError("Payment not found", "PAYMENT_NOT_FOUND")
        self._adopt(payment)
        invoice = await self.invoices.get_by_id(payment.invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        customer = await self.customers.get_by_id(invoice.customer_id)
        if customer is None or not customer.email:
            return None
        company = await self.company_settings.get_current()
        return render_email(
            "payment_receipt",
            to=customer.email,
            subject=f"Payment received for invoice {invoice.invoice_number}",
            customer=customer,
            invoice=invoice,
            payment=payment,
            balance=invoice.total - invoice.amount_paid,
            **self._base_context(company),
        )

    async def compose_invoice_reminder(self, invoice_id: uuid.UUID) -> OutgoingEmail | None:
        """Payment reminder, worded for where the invoice stands on the day
        it's actually sent. Returns None if it was paid or voided between
        being scheduled and being sent: no "please pay" after they paid."""
        invoice = await self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        self._adopt(invoice)
        if invoice.status not in REMINDABLE:
            return None
        customer = await self.customers.get_by_id(invoice.customer_id)
        if customer is None or not customer.email:
            return None
        company = await self.company_settings.get_current()
        days_past_due = (company_today(company.default_timezone) - invoice.due_date).days
        if days_past_due > 0:
            subject = f"Overdue: invoice {invoice.invoice_number} from {company.company_name}"
        elif days_past_due == 0:
            subject = f"Due today: invoice {invoice.invoice_number} from {company.company_name}"
        else:
            subject = f"Reminder: invoice {invoice.invoice_number} is due soon"
        return render_email(
            "invoice_reminder",
            to=customer.email,
            subject=subject,
            customer=customer,
            invoice=invoice,
            amount_due=invoice.total - invoice.amount_paid,
            days_past_due=days_past_due,
            **self._base_context(company),
        )

    async def compose_test_email(self, to: str) -> OutgoingEmail:
        company = await self.company_settings.get_current()
        return render_email(
            "test_email",
            to=to,
            subject=f"Test email from {company.company_name}",
            **self._base_context(company),
        )


    async def compose_statement(self, customer_id: uuid.UUID, start, end) -> OutgoingEmail | None:
        customer = await self.customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
        self._adopt(customer)
        if not customer.email:
            return None
        _, company, template, statement = await DocumentService(self.db).statement(customer_id, start, end)
        return render_email(
            "statement",
            to=customer.email,
            subject=f"{template.statement_title} from {company.company_name}: {start:%d %b %Y} to {end:%d %b %Y}",
            customer=customer,
            statement=statement,
            **self._base_context(company),
        )
