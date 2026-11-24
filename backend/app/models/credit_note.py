"""Credit notes: how an invoice that has gone out is reduced.

A tax invoice the customer holds is never changed in place, and once money
has been paid against it, it can't be voided either. A credit note is its own
numbered document (CN-0001) that names the invoice it reduces, with its own
VAT split, so the customer's records and the company's stay the same. The
invoice keeps its total; what's owed is total - amount_credited - amount_paid.

A credit note issued by mistake is voided (never deleted): its amount goes
back onto the invoice."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

ISSUED = "issued"
VOID = "void"


class CreditNote(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (UniqueConstraint("company_id", "credit_note_number", name="uq_credit_notes_company_number"),)

    credit_note_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # issued | void
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=ISSUED, server_default=ISSUED)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Why the invoice is reduced, printed on the credit note.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="credit_notes")
    items: Mapped[list["CreditNoteItem"]] = relationship(
        back_populates="credit_note", cascade="all, delete-orphan", order_by="CreditNoteItem.sort_order"
    )


class CreditNoteItem(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "credit_note_items"

    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    credit_note: Mapped["CreditNote"] = relationship(back_populates="items")
