"""What YGT tells a person: a reminder that an activity is due, a task
assigned to them, someone's update on a task. Each one is listed behind
the bell in the app, and can also go out by email and as a push message
to the phones and computers the person allowed (PushSubscription)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


class Notification(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    # A key makes a notification happen once: the same reminder isn't
    # repeated however often the per-minute check runs.
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notifications_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # activity_due | task_assigned | task_update | deal_no_next_step
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # Shown in the app in the person's language (from kind + params);
    # title/body are the English text for email and push.
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PushSubscription(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A phone or computer that agreed to receive YGT's push messages."""

    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
