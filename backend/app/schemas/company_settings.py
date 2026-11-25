import re
from decimal import Decimal
import uuid
from datetime import datetime
from typing import Literal

from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.countries import COUNTRIES, CURRENCIES


def clean_reply_to(value: str | None) -> str | None:
    """'a@x.co.za; B@x.co.za ' -> 'a@x.co.za, b@x.co.za' (max 3); '' -> None."""
    if value is None:
        return None
    parts = [p.strip().lower() for p in value.replace(";", ",").split(",") if p.strip()]
    if len(parts) > 3:
        raise ValueError("Give at most 3 reply addresses")
    for part in parts:
        if not re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", part):
            raise ValueError(f"{part} isn't an email address")
    return ", ".join(dict.fromkeys(parts)) or ""


class CompanySettingsUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=255)
    tax_number: str | None = Field(default=None, max_length=100)
    vat_registered: bool | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    tax_name: str | None = Field(default=None, min_length=1, max_length=20)
    default_tax_rate: Decimal | None = Field(default=None, ge=0, le=50, decimal_places=2)
    default_currency: str | None = Field(default=None, min_length=3, max_length=10)
    default_timezone: str | None = Field(default=None, max_length=50)

    @field_validator("country")
    @classmethod
    def _country(cls, value):
        if value is None:
            return value
        if value.upper() not in COUNTRIES:
            raise ValueError("Pick a country from the list")
        return value.upper()

    @field_validator("default_currency")
    @classmethod
    def _currency(cls, value):
        if value is None:
            return value
        if value.strip().upper() not in CURRENCIES:
            raise ValueError("Pick a currency from the list")
        return value.strip().upper()

    @field_validator("default_timezone")
    @classmethod
    def _timezone(cls, value):
        if value is None:
            return value
        try:
            ZoneInfo(value.strip())
        except Exception:
            raise ValueError("Use a time zone like Africa/Johannesburg or Africa/Nairobi")
        return value.strip()

    @field_validator("tax_name")
    @classmethod
    def _tax_name(cls, value):
        return value.strip() if value else value
    logo_url: str | None = Field(default=None, max_length=500)
    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    quote_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    po_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)

    # Outgoing email / SMTP. sender_email is who invoices appear to come
    # from; smtp_* are the credentials used to actually send them. Leaving
    # smtp_host unset falls back to the server-wide SMTP_* env vars.
    sender_name: str | None = Field(default=None, max_length=255)
    sender_email: EmailStr | None = None
    # Client replies go to: up to 3 addresses, comma-separated. "" clears it.
    reply_to_emails: str | None = Field(default=None, max_length=500)

    @field_validator("reply_to_emails")
    @classmethod
    def _reply_to(cls, value):
        return clean_reply_to(value)
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    smtp_use_tls: bool | None = None

    customer_term: Literal["customer", "client"] | None = None
    email_signature: str | None = Field(default=None, max_length=1000)

    reminders_enabled: bool | None = None
    reminder_offsets: list[int] | None = Field(default=None, max_length=10)

    annual_revenue_goal: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    financial_year_start_month: int | None = Field(default=None, ge=1, le=12)

    @field_validator("reminder_offsets")
    @classmethod
    def _normalize_offsets(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(not -60 <= day <= 365 for day in value):
            raise ValueError("reminder days must be between -60 and 365")
        return sorted(set(value))


class CompanySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    address: str | None
    phone: str | None = None
    website: str | None = None
    tax_number: str | None
    vat_registered: bool = False
    country: str = "ZA"
    tax_name: str = "VAT"
    default_tax_rate: Decimal = Decimal("15")
    default_currency: str
    default_timezone: str
    logo_url: str | None
    invoice_prefix: str
    quote_prefix: str
    po_prefix: str = "PO-"
    next_invoice_number: int
    next_quote_number: int
    payment_terms_days: int
    sender_name: str | None
    sender_email: str | None
    reply_to_emails: str | None = None
    smtp_host: str | None
    smtp_port: int | None
    smtp_username: str | None
    smtp_use_tls: bool
    # smtp_password is intentionally omitted: write-only, never echoed back.
    smtp_password_set: bool
    customer_term: str
    email_signature: str | None
    reminders_enabled: bool
    reminder_offsets: list[int]
    annual_revenue_goal: Decimal | None = None
    financial_year_start_month: int = 3
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row) -> "CompanySettingsOut":
        return cls.model_validate(
            {
                # Every column but the logo's bytes (deferred; served on their own).
                **{c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "logo_image"},
                "smtp_password_set": bool(row.smtp_password),
            }
        )


class TestEmailRequest(BaseModel):
    # Defaults to the requesting admin's own address when omitted.
    to: EmailStr | None = None


class TestEmailResult(BaseModel):
    sent_to: str


class CompanyProfileOut(BaseModel):
    """The non-sensitive slice of company settings every signed-in user
    needs (branding in the app shell, currency for display)."""

    model_config = ConfigDict(from_attributes=True)

    company_name: str
    # Printed on every document anyway; a new purchase order delivers here.
    address: str | None = None
    vat_registered: bool = False
    # Where the company trades and how its money and tax show.
    country: str = "ZA"
    tax_name: str = "VAT"
    default_tax_rate: Decimal = Decimal("15")
    default_currency: str
    logo_url: str | None
    customer_term: str
    email_signature: str | None = None
    # For each person's suggested signature.
    phone: str | None = None
    website: str | None = None
