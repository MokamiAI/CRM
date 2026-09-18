import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import InvoiceStatus, QuoteStatus
from app.models.invoice import Invoice, InvoiceItem
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.quote_repository import QuoteRepository
from app.schemas.invoice import InvoiceCreate, InvoiceFromQuote, InvoiceUpdate
from app.services.pricing import build_line_items

_ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    # PARTIALLY_PAID/PAID/OVERDUE are driven automatically by the payment
    # recording flow and the invoice status engine (later phases), not by
    # manual transition here.
    InvoiceStatus.DRAFT: {InvoiceStatus.SENT, InvoiceStatus.VOID},
    InvoiceStatus.SENT: {InvoiceStatus.VOID},
    InvoiceStatus.PARTIALLY_PAID: set(),
    InvoiceStatus.PAID: set(),
    InvoiceStatus.OVERDUE: {InvoiceStatus.VOID},
    InvoiceStatus.VOID: set(),
}


class InvoiceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.quotes = QuoteRepository(db)
        self.customers = CustomerRepository(db)
        self.company_settings = CompanySettingsRepository(db)

    async def _default_due_date(self, issue_date: date) -> date:
        settings_row = await self.company_settings.get_singleton()
        return issue_date + timedelta(days=settings_row.payment_terms_days)

    async def create_invoice(self, data: InvoiceCreate, created_by_id: uuid.UUID) -> Invoice:
        customer = await self.customers.get_by_id(data.customer_id)
        if customer is None or not customer.is_active:
            raise NotFoundError("Customer not found or inactive", "CUSTOMER_NOT_FOUND")

        items, subtotal, tax_total, total = build_line_items(InvoiceItem, data.items)
        invoice_number = await self.company_settings.reserve_next_invoice_number()
        due_date = data.due_date or await self._default_due_date(data.issue_date)

        invoice = Invoice(
            invoice_number=invoice_number,
            customer_id=data.customer_id,
            issue_date=data.issue_date,
            due_date=due_date,
            notes=data.notes,
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            created_by=created_by_id,
            items=items,
        )
        return await self.invoices.create(invoice)

    async def create_from_quote(
        self, quote_id: uuid.UUID, data: InvoiceFromQuote, created_by_id: uuid.UUID
    ) -> Invoice:
        quote = await self.quotes.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        if quote.status != QuoteStatus.ACCEPTED:
            raise ConflictError(
                "Only accepted quotes can be converted to an invoice", "QUOTE_NOT_ACCEPTED"
            )

        items, subtotal, tax_total, total = build_line_items(InvoiceItem, quote.items)
        invoice_number = await self.company_settings.reserve_next_invoice_number()
        issue_date = data.issue_date or date.today()
        due_date = data.due_date or await self._default_due_date(issue_date)

        invoice = Invoice(
            invoice_number=invoice_number,
            customer_id=quote.customer_id,
            quote_id=quote.id,
            issue_date=issue_date,
            due_date=due_date,
            notes=quote.notes,
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            created_by=created_by_id,
            items=items,
        )
        await self.invoices.create(invoice)
        quote.status = QuoteStatus.CONVERTED
        await self.quotes.save(quote)
        return invoice

    async def list_invoices(self, offset=0, limit=50, customer_id=None, status=None) -> list[Invoice]:
        return await self.invoices.list_all(
            offset=offset, limit=limit, customer_id=customer_id, status=status
        )

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        return invoice

    async def update_invoice(self, invoice_id: uuid.UUID, data: InvoiceUpdate) -> Invoice:
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise ConflictError("Only draft invoices can be edited", "INVOICE_NOT_EDITABLE")

        if data.issue_date is not None:
            invoice.issue_date = data.issue_date
        if data.due_date is not None:
            invoice.due_date = data.due_date
        if data.notes is not None:
            invoice.notes = data.notes
        if data.items is not None:
            items, subtotal, tax_total, total = build_line_items(InvoiceItem, data.items)
            invoice.items.clear()
            invoice.items.extend(items)
            invoice.subtotal = subtotal
            invoice.tax_total = tax_total
            invoice.total = total
        return await self.invoices.save(invoice)

    async def transition_status(self, invoice_id: uuid.UUID, new_status: InvoiceStatus) -> Invoice:
        invoice = await self.get_invoice(invoice_id)
        allowed = _ALLOWED_TRANSITIONS.get(invoice.status, set())
        if new_status not in allowed:
            raise ConflictError(
                f"Cannot move invoice from {invoice.status.value} to {new_status.value}",
                "INVOICE_INVALID_TRANSITION",
            )
        invoice.status = new_status
        return await self.invoices.save(invoice)

    async def delete_invoice(self, invoice_id: uuid.UUID) -> None:
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise ConflictError("Only draft invoices can be deleted", "INVOICE_NOT_DELETABLE")
        await self.invoices.delete(invoice)
