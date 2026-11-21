import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import PaymentMethod


class Payment(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class OnlinePayment(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """One attempt by a customer to pay an invoice online, through the
    company's own Paystack account (Settings > Online payments).

    Made when the customer presses "Pay" on the invoice's pay page, for
    whatever was still owed at that moment. It becomes `paid` once the
    provider confirms the charge and a Payment is recorded against the
    invoice; `reference` is unique, so a charge is recorded once however
    many times it is confirmed (return page, webhook, periodic check).
    `needs_attention`: the customer paid but the invoice no longer needed
    it (paid another way meanwhile); the owner refunds it or keeps it."""

    __tablename__ = "online_payments"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # pending | paid | needs_attention | not_started (Paystack refused to
    # open a checkout) | failed (declined; the customer may still retry on
    # the same checkout, so it is checked again) | abandoned (given up on)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)  # card, eft, ...
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
