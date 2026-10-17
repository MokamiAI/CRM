"""Customer-confirmed progress alongside the commercial sales pipeline."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


class McemJourney(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "mcem_journeys"
    __table_args__ = (UniqueConstraint("deal_id"), CheckConstraint("state IN ('draft', 'active', 'paused')"))
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")
    qualification_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_process: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assumptions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    commitments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dependencies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risks: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success_measure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    baseline: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    delivery_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    account_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class McemMilestone(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "mcem_milestones"
    __table_args__ = (UniqueConstraint("deal_id", "key"), CheckConstraint("status IN ('not_started', 'in_progress', 'confirmed')"))
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_started")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class McemEvidence(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "mcem_evidence"
    milestone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mcem_milestones.id", ondelete="CASCADE"), nullable=False, index=True)
    # Validated against a tenant-scoped source when added. The dated explanation
    # and source label remain as historical evidence if the source is removed.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class McemEvent(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "mcem_events"
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
