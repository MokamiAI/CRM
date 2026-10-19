import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactPerson(BaseModel):
    """The person you deal with at a company customer: saved as the
    customer's main (primary) contact."""

    name: str = Field(min_length=1, max_length=241)
    job_title: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email(cls, value):
        return value or None


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    delivery_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    contact: ContactPerson | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    delivery_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool | None = None
    custom_fields: dict[str, Any] | None = None
    marketing_opt_out: bool | None = None
    contact: ContactPerson | None = None


class CustomerOut(BaseModel):
    is_prospect: bool = False
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    billing_address: str | None
    delivery_address: str | None = None
    tax_number: str | None
    notes: str | None
    is_active: bool
    custom_fields: dict[str, Any] = {}
    marketing_opt_out: bool = False
    marketing_opt_out_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
