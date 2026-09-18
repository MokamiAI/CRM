from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class CompanySettings(UUIDPKMixin, TimestampMixin, Base):
    """Singleton-style table: the application expects exactly one row."""

    __tablename__ = "company_settings"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ZAR")
    default_timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Africa/Johannesburg"
    )
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invoice_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="INV-")
    quote_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="QUO-")
    next_invoice_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_quote_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Outgoing-email configuration for sending invoices/quotes/reminders.
    # When smtp_host is null, the app falls back to the SMTP_* env vars
    # in app/core/config.py (see app/services/email_settings.py).
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
