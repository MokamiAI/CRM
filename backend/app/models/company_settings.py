from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column

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
    # An uploaded logo (Settings > Documents), served at /public/logo/<id>
    # and linked through logo_url. Deferred: never loaded unless asked for.
    logo_image: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    logo_content_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    invoice_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="INV-")
    quote_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="QUO-")
    next_invoice_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_quote_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Purchase orders to suppliers: PO-0001, PO-0002...
    po_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="PO-", server_default="PO-")
    next_po_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # The year's revenue goal (won deals count towards it) and the month the
    # company's year starts: 3 = March, the usual South African financial year.
    annual_revenue_goal: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    financial_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")

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

    # Set by YGT's team in the admin site: nobody in the company can use the app.
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Customers can email the company's inbox at inbox+<inbox_token>@<inbound
    # domain>; the token says which company a new conversation belongs to.
    inbox_token: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)

    # An admin hid the Get started checklist on the dashboard.
    onboarding_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reminders_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminder_offsets: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [-3, 0, 7, 14]
    )
