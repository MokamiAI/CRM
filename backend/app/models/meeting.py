import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


class Meeting(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_meeting_duration"),
        CheckConstraint("status IN ('invited','accepted','declined','proposed','cancelled')", name="ck_meeting_status"),
    )
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), unique=True, nullable=False)
    organizer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    attendee_name: Mapped[str] = mapped_column(String(241), nullable=False)
    attendee_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_reason: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    proposed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
