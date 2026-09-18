import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPKMixin


class ReminderLog(UUIDPKMixin, Base):
    """Tracks which reminder emails have already been sent per invoice, to
    prevent the Celery beat schedule from sending duplicates."""

    __tablename__ = "reminder_logs"
    __table_args__ = (UniqueConstraint("invoice_id", "reminder_type", name="uq_reminder_invoice_type"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reminder_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="reminder_logs")
