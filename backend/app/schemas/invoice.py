import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InvoiceStatus


class InvoiceItemCreate(BaseModel):
    product_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal
    sort_order: int


class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    issue_date: date
    due_date: date | None = None
    notes: str | None = None
    items: list[InvoiceItemCreate] = Field(min_length=1)


class InvoiceFromQuote(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None


class InvoiceUpdate(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    items: list[InvoiceItemCreate] | None = Field(default=None, min_length=1)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    quote_id: uuid.UUID | None
    status: InvoiceStatus
    issue_date: date
    due_date: date
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    amount_paid: Decimal
    notes: str | None
    items: list[InvoiceItemOut]
    created_at: datetime
    updated_at: datetime
