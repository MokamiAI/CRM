import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    billing_address: str | None = None
    tax_number: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_active: bool | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    billing_address: str | None
    tax_number: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
