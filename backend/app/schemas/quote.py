import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QuoteStatus


class QuoteItemCreate(BaseModel):
    product_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class QuoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal
    sort_order: int


class QuoteCreate(BaseModel):
    customer_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    issue_date: date
    expiry_date: date | None = None
    notes: str | None = None
    # The client's purchase order number, quoted on the document.
    po_number: str | None = Field(default=None, max_length=60)
    # Your own reference: a project, job or site name.
    reference: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    items: list[QuoteItemCreate] = Field(min_length=1)


class QuoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    issue_date: date | None = None
    expiry_date: date | None = None
    notes: str | None = None
    # The client's purchase order number, quoted on the document.
    po_number: str | None = Field(default=None, max_length=60)
    # Your own reference: a project, job or site name.
    reference: str | None = Field(default=None, max_length=100)
    items: list[QuoteItemCreate] | None = Field(default=None, min_length=1)


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    deal_id: uuid.UUID | None
    status: QuoteStatus
    issue_date: date
    expiry_date: date | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    notes: str | None
    po_number: str | None = None
    reference: str | None = None
    title: str | None = None
    description: str | None = None
    items: list[QuoteItemOut]
    created_at: datetime
    updated_at: datetime


class QuoteAcceptOut(QuoteOut):
    """An accepted quote, with the draft invoice made from it (none when the
    plan had no room for another invoice this month)."""

    invoice_id: uuid.UUID | None = None
    invoice_number: str | None = None
