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
    issue_date: date
    expiry_date: date | None = None
    notes: str | None = None
    items: list[QuoteItemCreate] = Field(min_length=1)


class QuoteUpdate(BaseModel):
    issue_date: date | None = None
    expiry_date: date | None = None
    notes: str | None = None
    items: list[QuoteItemCreate] | None = Field(default=None, min_length=1)


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    status: QuoteStatus
    issue_date: date
    expiry_date: date | None
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    notes: str | None
    items: list[QuoteItemOut]
    created_at: datetime
    updated_at: datetime
