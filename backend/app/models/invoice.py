import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import InvoiceStatus


class Invoice(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("company_id", "invoice_number", name="uq_invoices_company_number"),
        # A quote's invoices: one for all of it, or one per part (deposit,
        # stages, balance). The quote is locked while it's invoiced, so it
        # can't be converted twice.
        Index("ix_invoices_quote_id", "quote_id"),
        # One invoice per recurring schedule per cycle.
        Index(
            "uq_invoices_recurring_cycle",
            "recurring_invoice_id",
            "recurrence_date",
            unique=True,
            postgresql_where=text("recurring_invoice_id IS NOT NULL"),
        ),
    )

    invoice_number: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InvoiceStatus.DRAFT,
        index=True,
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Taken off by credit notes (app/models/credit_note.py). The total stays
    # as the customer's tax invoice says; what's owed is the balance below.
    amount_credited: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The client's purchase order (order) number, quoted back on the document.
    po_number: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    # Your own reference for this document (project, job or site name).
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Made by a recurring schedule, for the cycle starting recurrence_date.
    recurring_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="invoices")
    quote: Mapped["Quote | None"] = relationship(back_populates="invoices")
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.sort_order"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    reminder_logs: Mapped[list["ReminderLog"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    credit_notes: Mapped[list["CreditNote"]] = relationship(back_populates="invoice", lazy="raise")

    @hybrid_property
    def balance_due(self):
        """Still owed: the total, less credit notes, less payments. Below
        zero when a credit note took off more than was left to pay: that's
        a refund owed to the customer (refund_due)."""
        # A new invoice, not yet flushed, has no defaults filled in yet.
        return Decimal(self.total or 0) - Decimal(self.amount_credited or 0) - Decimal(self.amount_paid or 0)

    @balance_due.inplace.expression
    @classmethod
    def _balance_due_expression(cls):
        return cls.total - cls.amount_credited - cls.amount_paid

    @property
    def amount_due(self):
        """What the customer still has to pay, never below zero."""
        return max(self.balance_due, 0)

    @property
    def refund_due(self):
        """Paid more than the invoice now comes to (after credit notes)."""
        return max(-self.balance_due, 0)


class InvoiceItem(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)  # the item: what it is
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # its description, printed under it
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")
