"""Credit notes: reduce an invoice that has gone out, before or after it's
been (partly) paid. See app/models/credit_note.py."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.credit_note import ISSUED, VOID, CreditNote, CreditNoteItem
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.credit_note import CreditNoteCreate
from app.services.payment_service import _recompute_status
from app.services.pricing import money
from app.services.reminder_service import company_today

# Sent to the customer: a credit note can reduce it. A draft is simply
# edited instead; a void invoice has nothing to reduce.
CREDITABLE = {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE, InvoiceStatus.PAID}
_ZERO = Decimal("0")


def _by_rate(items) -> dict[Decimal, Decimal]:
    out: dict[Decimal, Decimal] = {}
    for item in items:
        rate = Decimal(item.tax_rate)
        out[rate] = out.get(rate, _ZERO) + Decimal(item.line_total)
    return out


def split_credit(invoice: Invoice, earlier: list[CreditNote], kind: str, value: Decimal | None) -> tuple[dict[Decimal, Decimal], Decimal]:
    """The credit note's net amount per VAT rate, and its VAT.

    In proportion to the invoice's own figures, so a credit of a quarter of
    the invoice takes a quarter of its net at each rate and a quarter of its
    VAT. An amount comes out to exactly what was typed (VAT included); "rest"
    takes exactly what earlier credit notes left, to the cent."""
    total = Decimal(invoice.total)
    creditable = total - sum((Decimal(c.total) for c in earlier), _ZERO)
    if creditable <= 0:
        raise ConflictError("This invoice has already been credited in full", "INVOICE_FULLY_CREDITED")
    net = _by_rate(invoice.items)
    if kind == "amount":
        value = money(Decimal(value))
        if value > creditable:
            raise ConflictError(
                f"That's more than is left to credit on this invoice ({creditable:,.2f})", "CREDIT_TOO_LARGE"
            )
        if value < creditable:
            fraction = value / total
            tax = money(Decimal(invoice.tax_total) * fraction)
            share = {rate: money(amount * fraction) for rate, amount in net.items()}
            # Rounding per rate can leave a cent over or under: the biggest
            # line takes it, so the credit note is exactly the amount typed.
            if share:
                biggest = max(share, key=lambda r: abs(share[r]))
                share[biggest] += value - tax - sum(share.values(), _ZERO)
            else:
                share = {_ZERO: value - tax}
            return {r: a for r, a in share.items() if a != 0}, tax
    # The rest: whatever earlier credit notes didn't take, per rate and VAT.
    done = _by_rate([item for c in earlier for item in c.items])
    share = {rate: net.get(rate, _ZERO) - done.get(rate, _ZERO) for rate in set(net) | set(done)}
    tax = Decimal(invoice.tax_total) - sum((Decimal(c.tax_total) for c in earlier), _ZERO)
    return {r: a for r, a in share.items() if a != 0}, tax


class CreditNoteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)

    async def _invoice_locked(self, invoice_id: uuid.UUID) -> Invoice:
        # Locked and re-read, like recording a payment: two credit notes (or a
        # credit note and a payment) at once must not work from stale figures.
        invoice = await self.db.scalar(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .with_for_update()
            .options(selectinload(Invoice.items))
            .execution_options(populate_existing=True)
        )
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        return invoice

    async def _issued(self, invoice_id: uuid.UUID) -> list[CreditNote]:
        return list(
            await self.db.scalars(
                select(CreditNote)
                .where(CreditNote.invoice_id == invoice_id, CreditNote.status == ISSUED)
                .options(selectinload(CreditNote.items))
                .order_by(CreditNote.created_at)
            )
        )

    async def _settle(self, invoice: Invoice) -> None:
        """The invoice's status after its amount owed changed: paid once
        nothing is left, otherwise as its payments and due date say."""
        _recompute_status(invoice)
        if invoice.status in (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID):
            company = await self.company_settings.get_current()
            if invoice.due_date < company_today(company.default_timezone):
                invoice.status = InvoiceStatus.OVERDUE

    async def list_for_invoice(self, invoice_id: uuid.UUID) -> list[CreditNote]:
        return list(
            await self.db.scalars(
                select(CreditNote)
                .where(CreditNote.invoice_id == invoice_id)
                .options(selectinload(CreditNote.items))
                .order_by(CreditNote.created_at)
            )
        )

    async def list_all(self, customer_id: uuid.UUID | None = None, limit: int = 200) -> list[CreditNote]:
        stmt = select(CreditNote).options(selectinload(CreditNote.items)).order_by(CreditNote.created_at.desc()).limit(limit)
        if customer_id is not None:
            stmt = stmt.where(CreditNote.customer_id == customer_id)
        return list(await self.db.scalars(stmt))

    async def get(self, credit_note_id: uuid.UUID) -> CreditNote:
        note = await self.db.scalar(
            select(CreditNote).where(CreditNote.id == credit_note_id).options(selectinload(CreditNote.items))
        )
        if note is None:
            raise NotFoundError("Credit note not found", "CREDIT_NOTE_NOT_FOUND")
        return note

    async def create(self, invoice_id: uuid.UUID, data: CreditNoteCreate, created_by_id: uuid.UUID) -> CreditNote:
        invoice = await self._invoice_locked(invoice_id)
        if invoice.status not in CREDITABLE:
            raise ConflictError(
                "Only an invoice that has been sent can get a credit note. Edit a draft instead.", "INVOICE_NOT_CREDITABLE"
            )
        earlier = await self._issued(invoice.id)
        share, tax = split_credit(invoice, earlier, data.kind, data.value)
        subtotal = sum(share.values(), _ZERO)
        if subtotal + tax <= 0:
            raise ConflictError("There's nothing left to credit on this invoice", "INVOICE_FULLY_CREDITED")

        what = f"Credit against invoice {invoice.invoice_number}"
        items = [
            CreditNoteItem(description=what, details=None, quantity=Decimal("1"), unit_price=amount, tax_rate=rate, line_total=amount, sort_order=n)
            for n, (rate, amount) in enumerate(sorted(share.items()))
        ]
        note = CreditNote(
            credit_note_number=await self.company_settings.reserve_next_credit_note_number(),
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            status=ISSUED,
            issue_date=data.issue_date or date.today(),
            reason=data.reason,
            subtotal=subtotal,
            tax_total=tax,
            total=subtotal + tax,
            created_by=created_by_id,
            items=items,
        )
        self.db.add(note)
        invoice.amount_credited = Decimal(invoice.amount_credited or 0) + note.total
        await self._settle(invoice)
        await self.db.flush()
        note.invoice_number = invoice.invoice_number
        return note

    async def void(self, credit_note_id: uuid.UUID, voided_by_id: uuid.UUID) -> CreditNote:
        """A credit note issued by mistake: it stays on record, marked void,
        and its amount goes back onto the invoice."""
        note = await self.get(credit_note_id)
        invoice = await self._invoice_locked(note.invoice_id)
        if note.status != ISSUED:
            raise ConflictError("This credit note is already void", "CREDIT_NOTE_VOID")
        if invoice.status == InvoiceStatus.VOID:
            raise ConflictError("The invoice is void", "INVOICE_VOID")
        note.status = VOID
        note.voided_at = datetime.now(timezone.utc)
        note.voided_by = voided_by_id
        invoice.amount_credited = Decimal(invoice.amount_credited or 0) - Decimal(note.total)
        await self._settle(invoice)
        await self.db.flush()
        note.invoice_number = invoice.invoice_number
        return note

    async def with_numbers(self, notes: list[CreditNote]) -> list[CreditNote]:
        """Each credit note's invoice number, for lists and the response."""
        ids = {n.invoice_id for n in notes}
        if ids:
            numbers = dict((await self.db.execute(select(Invoice.id, Invoice.invoice_number).where(Invoice.id.in_(ids)))).all())
            for n in notes:
                n.invoice_number = numbers.get(n.invoice_id)
        return notes
