import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentCreate

# Invoices in these statuses cannot receive a new payment: DRAFT hasn't
# been sent to the customer yet, VOID and PAID have nothing left to pay.
_NOT_PAYABLE = {InvoiceStatus.DRAFT, InvoiceStatus.VOID, InvoiceStatus.PAID}


def _recompute_status(invoice: Invoice) -> None:
    if invoice.amount_paid <= 0:
        invoice.status = InvoiceStatus.SENT
    elif invoice.amount_paid >= invoice.total:
        invoice.status = InvoiceStatus.PAID
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.payments = PaymentRepository(db)
        self.invoices = InvoiceRepository(db)

    async def record_payment(
        self, invoice_id: uuid.UUID, data: PaymentCreate, recorded_by_id: uuid.UUID
    ) -> Payment:
        invoice = await self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        if invoice.status in _NOT_PAYABLE:
            raise ConflictError(
                f"Cannot record a payment against an invoice in status {invoice.status.value}",
                "INVOICE_NOT_PAYABLE",
            )

        remaining = invoice.total - invoice.amount_paid
        if data.amount > remaining:
            raise ConflictError(
                f"Payment amount {data.amount} exceeds the remaining balance {remaining}",
                "PAYMENT_EXCEEDS_BALANCE",
            )

        payment = Payment(
            invoice_id=invoice_id,
            amount=data.amount,
            method=data.method,
            reference=data.reference,
            paid_at=data.paid_at or datetime.now(timezone.utc),
            recorded_by=recorded_by_id,
            notes=data.notes,
        )
        await self.payments.create(payment)

        invoice.amount_paid = invoice.amount_paid + data.amount
        _recompute_status(invoice)
        await self.invoices.save(invoice)
        return payment

    async def list_payments(self, invoice_id: uuid.UUID) -> list[Payment]:
        invoice = await self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        return await self.payments.list_for_invoice(invoice_id)

    async def delete_payment(self, payment_id: uuid.UUID) -> None:
        payment = await self.payments.get_by_id(payment_id)
        if payment is None:
            raise NotFoundError("Payment not found", "PAYMENT_NOT_FOUND")

        invoice = await self.invoices.get_by_id(payment.invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
        if invoice.status == InvoiceStatus.VOID:
            raise ConflictError("Cannot modify payments on a void invoice", "INVOICE_VOID")

        await self.payments.delete(payment)
        invoice.amount_paid = invoice.amount_paid - payment.amount
        _recompute_status(invoice)
        await self.invoices.save(invoice)
