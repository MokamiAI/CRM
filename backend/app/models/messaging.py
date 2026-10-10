import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

CONVERSATION_STATUSES = ("open", "closed")
CHANNELS = ("email", "whatsapp", "sms")
# in: from the customer; out: from the business to the customer;
# note: internal, never sent to the customer.
MESSAGE_DIRECTIONS = ("in", "out", "note")
MESSAGE_STATUSES = ("received", "queued", "sent", "failed")


def _user_fk():
    return ForeignKey("users.id", ondelete="SET NULL")


class Conversation(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A thread between the business and one customer (or an unknown sender
    who emailed the company's inbox address). Replies come back through
    reply+<token>@<inbound domain>, which identifies the thread."""

    __tablename__ = "conversations"

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email", index=True)
    # Who the thread is with when they aren't (yet) a customer record.
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # WhatsApp/SMS: international format digits, e.g. 27821234567.
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True, index=True)
    token: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_message_preview: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # RFC 5322 Message-ID, so mail clients keep replies in one thread.
    email_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The provider's id for a WhatsApp/SMS message.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class TeamChannel(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """Internal team chat channel ("General", "Sales", ...)."""

    __tablename__ = "team_channels"

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)


class TeamMessage(TenantMixin, UUIDPKMixin, Base):
    __tablename__ = "team_messages"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk(), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


CONNECTION_KINDS = ("email_in", "whatsapp", "sms")


class ChannelConnection(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A company's own account for one messaging channel, entered by its
    admin in Settings: the mailbox the app reads replies from (email_in),
    a WhatsApp Business number, or an SMS provider account.

    `settings` holds non-secret values (hosts, number ids, sender ids);
    `secrets` is one encrypted blob (passwords, API tokens) that the API
    never returns. Providers post incoming messages to
    /public/channels/<webhook_token>/..., which identifies the company."""

    __tablename__ = "channel_connections"
    __table_args__ = (UniqueConstraint("company_id", "kind", name="uq_channel_connections_company_kind"),)

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    secrets: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_token: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="untested")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
