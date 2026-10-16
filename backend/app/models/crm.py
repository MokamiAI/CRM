"""Relationship-management objects that sit around the billing core.

The shape follows the standard CRM object model (HubSpot, Pipedrive):
a customer is the company/account; contacts are the people there; deals
are sales opportunities moving through a pipeline; activities are the
scheduled work (calls, meetings, tasks) that move deals forward; notes
are free-text history. Everything hangs off a customer so the customer
record can show one chronological timeline.
"""
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ActivityType, DealStage

_user_fk = lambda: ForeignKey("users.id", ondelete="SET NULL")  # noqa: E731


class Contact(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # The person invoices and quotes are addressed to. At most one per
    # customer is primary (enforced in ContactService).
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)



class Deal(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (CheckConstraint("priority IN ('high', 'medium', 'low')", name="ck_deals_priority"),)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True, index=True)
    stage: Mapped[DealStage] = mapped_column(
        Enum(DealStage, name="deal_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DealStage.LEAD,
        index=True,
    )
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # How much this deal matters to the business: high, medium or low.
    # High deals lead each pipeline column; urgency orders within a level.
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium", server_default="medium")
    custom_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)


class Activity(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (CheckConstraint("status IN ('todo', 'in_progress', 'blocked', 'done')", name="ck_activities_status"),)

    type: Mapped[ActivityType] = mapped_column(
        Enum(ActivityType, name="activity_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ActivityType.TASK,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A task's progress, kept in step with `done`: todo, in_progress,
    # blocked, done. The assignee reports it with a note (TaskUpdate).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo", server_default="todo")
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)


class Note(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "notes"

    body: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)


TASK_STATUSES = ("todo", "in_progress", "blocked", "done")


class TaskUpdate(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """What someone did on an activity: a status change, a note, or both.
    Done and Blocked need a note, so the person who assigned it knows."""

    __tablename__ = "task_updates"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
