import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import PurchaseOrderStatus
from app.schemas.quote import QuoteItemCreate


def _blank_to_none(value):
    return value.strip() or None if isinstance(value, str) else value


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    tax_number: str | None = Field(default=None, max_length=100)
    address: str | None = None
    notes: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _empty_email(cls, value):
        return _blank_to_none(value)


class SupplierUpdate(SupplierCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    tax_number: str | None
    address: str | None
    notes: str | None
    is_active: bool
    created_at: datetime


# A purchase order line has the same shape as a quote line.
PurchaseOrderItemCreate = QuoteItemCreate


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal
    sort_order: int


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    issue_date: date
    delivery_date: date | None = None
    delivery_address: str | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: uuid.UUID | None = None
    issue_date: date | None = None
    delivery_date: date | None = None
    delivery_address: str | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] | None = Field(default=None, min_length=1)


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    po_number: str
    supplier_id: uuid.UUID
    status: PurchaseOrderStatus
    issue_date: date
    delivery_date: date | None
    delivery_address: str | None
    reference: str | None
    notes: str | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    items: list[PurchaseOrderItemOut]
    created_at: datetime
    updated_at: datetime


class LineTemplateItem(BaseModel):
    product_id: uuid.UUID | None = None
    description: str = Field(min_length=1, max_length=2000)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class LineTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    items: list[LineTemplateItem] = Field(min_length=1, max_length=100)


class LineTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    items: list[LineTemplateItem]
    created_by: uuid.UUID | None
    created_at: datetime
