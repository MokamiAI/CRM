"""Spending: the bills and expenses a company pays (rent, salaries, stock,
fuel), one-off or on a schedule. With payments received, they give money in,
money out and profit (app/services/cost_service.py). Money counts when it
moves: a cost counts when it's paid, not when the bill arrives."""
import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

# The ready-made categories; a company can also type its own.
CATEGORIES = ("rent", "salaries", "stock", "transport", "marketing", "utilities", "software", "other")


class RecurringCost(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A bill that comes back: rent on the 1st, insurance each month. Each
    cycle makes a bill to pay a week before it's due; it's never marked paid
    by itself, so the figures stay true."""

    __tablename__ = "recurring_costs"

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # recurring.FREQUENCIES
    # The first due date; later ones keep its day of the month.
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Cost(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "costs"
    __table_args__ = (
        CheckConstraint("status IN ('due', 'paid')", name="ck_costs_status"),
        CheckConstraint("amount > 0", name="ck_costs_amount_positive"),
        # A cycle of a recurring bill is made once.
        UniqueConstraint("recurring_cost_id", "recurrence_date", name="uq_costs_recurrence"),
        # A purchase order is recorded as a cost once.
        UniqueConstraint("purchase_order_id", name="uq_costs_purchase_order"),
    )

    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # What was or will be paid, VAT included.
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # When the bill is due (or the day of a one-off purchase).
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="due")
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True
    )
    recurring_cost_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_costs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A photo or PDF of the slip; the bytes load only when it's opened.
    receipt_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
