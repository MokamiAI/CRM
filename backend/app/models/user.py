import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import UserRole


class User(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.STAFF,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # UI language (ISO 639 code, see enums.SUPPORTED_LANGUAGES). Stored per
    # user so it follows them across devices.
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    # When this person finished (or skipped) the first-run guided tour.
    tour_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Plain text, line by line, added to the emails this person sends from
    # Messages. Empty: the company signature, else name and company.
    email_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When this person clicked the link we emailed them, proving the inbox is
    # theirs. Until then the app asks them to; YGT admin access needs it.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_platform_admin(self) -> bool:
        """YGT's own team: emails listed in PLATFORM_ADMIN_EMAILS can use the admin site."""
        from app.core.config import settings

        # A confirmed email too: otherwise whoever signs up with the address
        # first (before its owner) would get the keys to every company.
        return self.email_verified_at is not None and self.email.lower() in settings.platform_admins

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(UUIDPKMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
