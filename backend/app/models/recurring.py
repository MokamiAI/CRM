import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

FREQUENCIES = ("weekly", "monthly", "quarterly", "yearly")


class RecurringInvoice(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A retainer or contract: a draft invoice made for a customer on a
    schedule (app/services/recurring_service.py). Drafts are never sent by
    themselves; a person reviews and sends each one."""

    __tablename__ = "recurring_invoices"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # FREQUENCIES
    # The first invoice date; later dates keep its day of the month (the
    # 31st becomes the last day of shorter months).
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Days to pay; none = the company's usual payment terms.
    due_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Line items as entered: description, quantity, unit_price, tax_rate, product_id.
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
