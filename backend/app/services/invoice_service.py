import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import InvoiceStatus, QuoteStatus
from app.models.invoice import Invoice, InvoiceItem
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.quote_repository import QuoteRepository
from app.schemas.invoice import InvoiceCreate, InvoiceFromQuote, InvoiceItemCreate, InvoicePartFromQuote, InvoiceUpdate
from app.services.pricing import build_line_items, money

_ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    # PARTIALLY_PAID/PAID are set by the payment recording flow
    # (app/services/payment_service.py); OVERDUE is set by the invoice
    # status engine below. Neither is reachable through this manual
    # transition table.
    InvoiceStatus.DRAFT: {InvoiceStatus.SENT, InvoiceStatus.VOID},
    InvoiceStatus.SENT: {InvoiceStatus.VOID},
    InvoiceStatus.PARTIALLY_PAID: set(),
    InvoiceStatus.PAID: set(),
    InvoiceStatus.OVERDUE: {InvoiceStatus.VOID},
    InvoiceStatus.VOID: set(),
}

# Invoices in these statuses can lapse into OVERDUE once past due_date.
# DRAFT hasn't been sent yet, PAID/VOID/OVERDUE have nothing further to do.
_OVERDUE_ELIGIBLE = {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID}


class InvoiceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.invoices = InvoiceRepository(db)
        self.quotes = QuoteRepository(db)
        self.customers = CustomerRepository(db)
        self.company_settings = CompanySettingsRepository(db)

    async def _default_due_date(self, issue_date: date) -> date:
        settings_row = await self.company_settings.get_current()
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
            po_number=(data.po_number or "").strip() or None,
            reference=(data.reference or "").strip() or None,
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
        quote = await self.quotes.get_for_update(quote_id)
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
            po_number=((data.po_number or "").strip() or None) or quote.po_number,
            reference=((data.reference or "").strip() or None) or quote.reference,
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

    # ---------- A quote invoiced in parts (deposit, stages, balance) ----------
    # Every part is worked out from the quote's own stored figures: its net
    # amount per VAT rate (discount lines included) and its VAT total as the
    # quote rounded it, line by line. A percentage or an amount takes that
    # share of each; the balance takes exactly what the earlier parts left.
    # So the parts always add up to the quote, VAT included, to the cent.

    async def _quote_invoices(self, quote_id: uuid.UUID, with_items: bool = False) -> list[Invoice]:
        stmt = select(Invoice).where(Invoice.quote_id == quote_id, Invoice.status != InvoiceStatus.VOID).order_by(Invoice.created_at)
        if with_items:
            stmt = stmt.options(selectinload(Invoice.items))
        return list((await self.db.scalars(stmt)).all())

    @staticmethod
    def _invoiced(invoices: list[Invoice]) -> Decimal:
        return sum((Decimal(i.total) for i in invoices), Decimal("0"))

    @staticmethod
    def _whole_draft(quote, invoices: list[Invoice]) -> tuple[Invoice | None, bool]:
        """The one draft covering the whole quote, and whether it's still as
        acceptance made it. Edited (its lines, dates or notes changed since),
        it's the person's work and is never replaced."""
        if len(invoices) != 1:
            return None, False
        only = invoices[0]
        if only.status != InvoiceStatus.DRAFT or Decimal(only.amount_paid or 0) != 0 or Decimal(only.total) < Decimal(quote.total):
            return None, False
        untouched = only.updated_at == only.created_at and Decimal(only.total) == Decimal(quote.total)
        return only, untouched

    async def quote_billing(self, quote_id: uuid.UUID) -> dict:
        quote = await self.quotes.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        invoices = await self._quote_invoices(quote.id)
        invoiced = self._invoiced(invoices)
        draft, untouched = self._whole_draft(quote, invoices)
        return {
            "total": quote.total, "invoiced": invoiced, "remaining": max(Decimal("0"), Decimal(quote.total) - invoiced),
            "invoices": invoices,
            "draft_to_replace": draft if draft is not None and untouched else None,
            "draft_edited": draft if draft is not None and not untouched else None,
        }

    async def create_part_from_quote(self, quote_id: uuid.UUID, data: InvoicePartFromQuote, created_by_id: uuid.UUID) -> Invoice:
        """An invoice for part of an accepted quote: a percentage, an amount
        (VAT included) or the balance still to invoice."""
        quote = await self.quotes.get_for_update(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        if quote.status not in (QuoteStatus.ACCEPTED, QuoteStatus.CONVERTED):
            raise ConflictError("Only an accepted quote can be invoiced", "QUOTE_NOT_ACCEPTED")
        invoices = await self._quote_invoices(quote.id, with_items=True)
        draft, untouched = self._whole_draft(quote, invoices)
        if draft is not None and data.replace_draft:
            if not untouched:
                raise ConflictError(
                    "The draft invoice for this quote was edited, so it isn't replaced. Delete or void it first.", "QUOTE_DRAFT_EDITED"
                )
            await self.invoices.delete(draft)
            await self.db.flush()
            invoices = []

        total = Decimal(quote.total)
        remaining = total - self._invoiced(invoices)
        if remaining <= 0:
            raise ConflictError("This quote is already fully invoiced", "QUOTE_FULLY_INVOICED")

        # The quote's net per VAT rate, and what the earlier parts took.
        net: dict[Decimal, Decimal] = {}
        for item in quote.items:
            net[Decimal(item.tax_rate)] = net.get(Decimal(item.tax_rate), Decimal("0")) + Decimal(item.line_total)
        done: dict[Decimal, Decimal] = {}
        for invoice in invoices:
            for item in invoice.items:
                done[Decimal(item.tax_rate)] = done.get(Decimal(item.tax_rate), Decimal("0")) + Decimal(item.line_total)
        done_tax = sum((Decimal(i.tax_total) for i in invoices), Decimal("0"))

        if data.kind == "balance":
            rates = sorted(set(net) | set(done))
            share = {rate: net.get(rate, Decimal("0")) - done.get(rate, Decimal("0")) for rate in rates}
            tax = Decimal(quote.tax_total) - done_tax
            part_text = None
        else:
            fraction = data.value / Decimal("100") if data.kind == "percent" else (data.value / total if total else Decimal("0"))
            share = {rate: money(amount * fraction) for rate, amount in net.items()}
            tax = money(Decimal(quote.tax_total) * fraction)
            part_text = f"{(fraction * 100).quantize(Decimal('0.1')).normalize():f}%"
            # A percentage or an amount can't be more than is left.
            if sum(share.values()) + tax > remaining + Decimal("0.01"):
                raise ConflictError("That's more than is left to invoice on this quote", "QUOTE_PART_TOO_LARGE")
        share = {rate: amount for rate, amount in share.items() if amount != 0}
        subtotal = sum(share.values(), Decimal("0"))
        if subtotal + tax <= 0:
            raise ConflictError("There's nothing left to invoice on this quote", "QUOTE_PART_TOO_LARGE")

        label = (data.label or "").strip() or ("Balance" if data.kind == "balance" else "Deposit" if not invoices else "Progress payment")
        what = f"{label} of quote {quote.quote_number}" if part_text is None else f"{label}: {part_text} of quote {quote.quote_number}"
        # Built here, not from request lines: every figure comes from the
        # quote and its invoices, never from the caller.
        items = [
            InvoiceItem(product_id=None, description=what, details=quote.title, quantity=Decimal("1"), unit_price=amount,
                        tax_rate=rate, line_total=amount, sort_order=n)
            for n, (rate, amount) in enumerate(sorted(share.items()))
        ]
        issue_date = date.today()
        invoice = Invoice(
            invoice_number=await self.company_settings.reserve_next_invoice_number(),
            customer_id=quote.customer_id,
            quote_id=quote.id,
            issue_date=issue_date,
            due_date=data.due_date or await self._default_due_date(issue_date),
            notes=quote.notes,
            po_number=quote.po_number,
            reference=quote.reference,
            subtotal=subtotal,
            # The quote's own VAT share, so the parts' VAT adds up to the quote's.
            tax_total=tax,
            total=subtotal + tax,
            created_by=created_by_id,
            items=items,
        )
        await self.invoices.create(invoice)
        quote.status = QuoteStatus.CONVERTED
        await self.quotes.save(quote)
        return invoice

    async def list_invoices(self, offset=0, limit=50, customer_id=None, status=None, sort="created") -> list[Invoice]:
        return await self.invoices.list_all(
            offset=offset, limit=limit, customer_id=customer_id, status=status, sort=sort
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
        if data.po_number is not None:
            invoice.po_number = data.po_number.strip() or None
        if data.reference is not None:
            invoice.reference = data.reference.strip() or None
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

    async def correct(self, invoice_id: uuid.UUID, created_by_id: uuid.UUID) -> Invoice:
        """Edit for an invoice that has gone out: a tax invoice the customer
        holds is never changed in place. It is voided and a draft copy (same
        customer, lines, notes and references, a new number) is returned to
        fix and send. Only before any payment: money received stays tied to
        the invoice it paid. The lock makes a double click one copy."""
        await self.invoices.get_for_update(invoice_id)
        invoice = await self.get_invoice(invoice_id)
        if invoice.status not in (InvoiceStatus.SENT, InvoiceStatus.OVERDUE) or Decimal(invoice.amount_paid or 0) > 0:
            raise ConflictError("Only a sent invoice with no payments can be corrected", "INVOICE_NOT_CORRECTABLE")
        invoice.status = InvoiceStatus.VOID
        await self.invoices.save(invoice)
        items = sorted(invoice.items, key=lambda i: i.sort_order)
        return await self.create_invoice(
            InvoiceCreate(
                customer_id=invoice.customer_id,
                issue_date=date.today(),
                notes=invoice.notes,
                po_number=invoice.po_number,
                reference=invoice.reference,
                items=[
                    InvoiceItemCreate(product_id=i.product_id, description=i.description, details=i.details, quantity=i.quantity, unit_price=i.unit_price, tax_rate=i.tax_rate)
                    for i in items
                ],
            ),
            created_by_id=created_by_id,
        )

    async def delete_invoice(self, invoice_id: uuid.UUID) -> None:
        invoice = await self.get_invoice(invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise ConflictError("Only draft invoices can be deleted", "INVOICE_NOT_DELETABLE")
        await self.invoices.delete(invoice)

    async def refresh_overdue_invoices(self) -> int:
        """Flips SENT/PARTIALLY_PAID invoices whose due_date has passed to
        OVERDUE. Called on-demand via the API and on a schedule by the
        Celery beat task in app/tasks/invoice_tasks.py."""
        result = await self.db.execute(
            select(Invoice).where(
                Invoice.status.in_(_OVERDUE_ELIGIBLE), Invoice.due_date < date.today()
            )
        )
        invoices = list(result.scalars().all())
        for invoice in invoices:
            invoice.status = InvoiceStatus.OVERDUE
        await self.db.flush()
        return len(invoices)
