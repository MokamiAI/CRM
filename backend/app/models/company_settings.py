from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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

    # Automated payment reminders (app/services/reminder_service.py). Each
    # offset is a day relative to the invoice due date: -3 = three days
    # before, 0 = on the day, 7 = a week overdue.
    # What the business calls the people it sells to: "customer" or
    # "client". Purely a UI wording choice, applied in every language.
    customer_term: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")

    # Plain-text sign-off for invoice, quote, receipt and reminder emails,
    # and for people who haven't set their own signature.
    email_signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    # How invoices, quotes and statements look (Settings > Documents); see
    # app/schemas/documents.py for the fields and their defaults.
    document_template: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Customers can email the company's inbox at inbox+<inbox_token>@<inbound
    # domain>; the token says which company a new conversation belongs to.
    inbox_token: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)

    # An admin hid the Get started checklist on the dashboard.
    onboarding_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminder_offsets: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [-3, 0, 7, 14]
    )
