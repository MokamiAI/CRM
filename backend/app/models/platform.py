"""Platform-level records: what YGT's own team works with in the admin site
(errors, activity, help desk, contact requests, session bookings, refunds).

ErrorLog, AuditEvent, ContactRequest, PlatformSetting and PasswordReset are
not tenant-scoped: they span companies or exist before anyone signs in.
Tickets, bookings and refunds belong to a company (TenantMixin) so a
company only ever sees its own; the admin site reads them across companies."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


def _company_fk(nullable: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=nullable, index=True)


class ErrorLog(UUIDPKMixin, Base):
    """An unexpected server error or failed background job."""

    __tablename__ = "error_logs"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    company_id: Mapped[uuid.UUID | None] = _company_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="api")  # api | task
    request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_type: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    traceback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(UUIDPKMixin, Base):
    """One change someone made (any POST/PUT/PATCH/DELETE), or a sign-in."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_company_created", "company_id", "created_at"),)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    company_id: Mapped[uuid.UUID | None] = _company_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(300), nullable=False)  # e.g. /invoices/{invoice_id}/send
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SupportTicket(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"

    number: Mapped[int] = mapped_column(Integer, Identity(start=1001), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="question")
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")  # low | normal | high
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    # Scale plan: priority support, so these go to the top of YGT's queue.
    priority_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Who spoke last decides whose turn it is in the queue.
    last_from_platform: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketMessage(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "ticket_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    from_platform: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Notes YGT's team keeps for itself; the company never sees these.
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ContactRequest(UUIDPKMixin, TimestampMixin, Base):
    """The Contact us form on the public pages."""

    __tablename__ = "contact_requests"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    topic: Mapped[str] = mapped_column(String(20), nullable=False, default="sales")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", index=True)  # new | contacted | closed
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SessionBooking(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A session a company booked with YGT's team (onboarding, help, training)."""

    __tablename__ = "session_bookings"
    # One booking per slot, across every company.
    __table_args__ = (Index("uq_session_bookings_slot", "starts_at", unique=True, postgresql_where=text("status = 'booked'")),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    topic: Mapped[str] = mapped_column(String(20), nullable=False, default="onboarding")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")  # booked | cancelled
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False)
    attendee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # calendar invite revision
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformSetting(Base):
    """Small platform-wide settings edited in the admin site (e.g. when
    sessions can be booked). One JSON value per key."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PasswordReset(UUIDPKMixin, Base):
    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BillingRefund(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A refund YGT gave a company on one of its subscription payments."""

    __tablename__ = "billing_refunds"

    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("billing_payments.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | processed | failed
    paystack_refund_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_email: Mapped[str] = mapped_column(String(255), nullable=False)
