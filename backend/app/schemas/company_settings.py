import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CompanySettingsUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    tax_number: str | None = Field(default=None, max_length=100)
    default_currency: str | None = Field(default=None, min_length=3, max_length=10)
    default_timezone: str | None = Field(default=None, max_length=50)
    logo_url: str | None = Field(default=None, max_length=500)
    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    quote_prefix: str | None = Field(default=None, min_length=1, max_length=20)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)

    # Outgoing email / SMTP. sender_email is who invoices appear to come
    # from; smtp_* are the credentials used to actually send them. Leaving
    # smtp_host unset falls back to the server-wide SMTP_* env vars.
    sender_name: str | None = Field(default=None, max_length=255)
    sender_email: EmailStr | None = None
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    smtp_use_tls: bool | None = None

    customer_term: Literal["customer", "client"] | None = None
    email_signature: str | None = Field(default=None, max_length=1000)

    reminders_enabled: bool | None = None
    reminder_offsets: list[int] | None = Field(default=None, max_length=10)

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
    tax_number: str | None
    default_currency: str
    default_timezone: str
    logo_url: str | None
    invoice_prefix: str
    quote_prefix: str
    next_invoice_number: int
    next_quote_number: int
    payment_terms_days: int
    sender_name: str | None
    sender_email: str | None
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
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row) -> "CompanySettingsOut":
        return cls.model_validate(
            {
                **{c.name: getattr(row, c.name) for c in row.__table__.columns},
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
    default_currency: str
    logo_url: str | None
    customer_term: str
    email_signature: str | None = None
