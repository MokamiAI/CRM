import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import InvoiceStatus
from app.schemas.invoice import InvoiceItemCreate

Frequency = Literal["weekly", "monthly", "quarterly", "yearly"]


class RecurringInvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    frequency: Frequency = "monthly"
    start_date: date
    end_date: date | None = None
    due_days: int | None = Field(default=None, ge=0, le=365)
    reference: str | None = Field(default=None, max_length=100)
    po_number: str | None = Field(default=None, max_length=60)
    notes: str | None = None
    items: list[InvoiceItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date must be on or after the start date")
        return self


class RecurringInvoiceUpdate(BaseModel):
    frequency: Frequency | None = None
    next_run_date: date | None = None
    end_date: date | None = None
    due_days: int | None = Field(default=None, ge=0, le=365)
    reference: str | None = Field(default=None, max_length=100)
    po_number: str | None = Field(default=None, max_length=60)
    notes: str | None = None
    items: list[InvoiceItemCreate] | None = Field(default=None, min_length=1)


class RecurringItemOut(BaseModel):
    product_id: uuid.UUID | None = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal


class RecurringInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    frequency: Frequency
    start_date: date
    next_run_date: date
    end_date: date | None
    due_days: int | None
    reference: str | None
    po_number: str | None
    notes: str | None
    items: list[RecurringItemOut]
    active: bool
    created_at: datetime
    # Per invoice, incl. VAT, as the next draft will be priced.
    total: Decimal = Decimal("0")


class RecurringInvoiceMade(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    issue_date: date
    status: InvoiceStatus
    total: Decimal


class RecurringInvoiceDetail(RecurringInvoiceOut):
    invoices: list[RecurringInvoiceMade] = []
