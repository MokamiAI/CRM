import uuid
from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import InvoiceStatus


class InvoiceItemCreate(BaseModel):
    product_id: uuid.UUID | None = None
    description: str = Field(min_length=1)  # the item
    details: str | None = Field(default=None, max_length=5000)  # its description
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    description: str
    details: str | None = None
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
    # The client's purchase order number, quoted on the document.
    po_number: str | None = Field(default=None, max_length=60)
    # Your own reference: a project, job or site name.
    reference: str | None = Field(default=None, max_length=100)
    items: list[InvoiceItemCreate] = Field(min_length=1)


class InvoiceFromQuote(BaseModel):
    issue_date: date | None = None
    # The client's purchase order number, quoted on the document.
    po_number: str | None = Field(default=None, max_length=60)
    # Your own reference: a project, job or site name.
    reference: str | None = Field(default=None, max_length=100)
    due_date: date | None = None


class InvoicePartFromQuote(BaseModel):
    """Part of an accepted quote as its own invoice: a deposit, a stage, or
    whatever is still to be invoiced (the balance)."""

    kind: Literal["percent", "amount", "balance"]
    # A percentage of the quote (percent), or an amount including VAT (amount).
    value: Decimal | None = Field(default=None, gt=0)
    # What it's for, printed on the invoice: "Deposit", "Stage 2: roofing".
    label: str | None = Field(default=None, max_length=60)
    due_date: date | None = None
    # The draft made when the quote was accepted covers all of it: replace it.
    replace_draft: bool = False

    @model_validator(mode="after")
    def _value_needed(self):
        if self.kind != "balance" and self.value is None:
            raise ValueError("value is needed for a percent or an amount")
        if self.kind == "percent" and self.value > 100:
            raise ValueError("a percentage is at most 100")
        return self


class QuoteBillingInvoice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    status: InvoiceStatus
    total: Decimal
    amount_paid: Decimal


class QuoteBilling(BaseModel):
    """How much of a quote is invoiced so far."""

    total: Decimal
    invoiced: Decimal
    remaining: Decimal
    invoices: list[QuoteBillingInvoice]
    # The one untouched draft that covers the whole quote, which invoicing
    # in parts would replace.
    draft_to_replace: QuoteBillingInvoice | None = None
    # That draft, edited since: it's the person's work and isn't replaced.
    draft_edited: QuoteBillingInvoice | None = None


class InvoiceUpdate(BaseModel):
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = None
    # The client's purchase order number, quoted on the document.
    po_number: str | None = Field(default=None, max_length=60)
    # Your own reference: a project, job or site name.
    reference: str | None = Field(default=None, max_length=100)
    items: list[InvoiceItemCreate] | None = Field(default=None, min_length=1)


class OverdueRefreshResult(BaseModel):
    updated: int


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
    po_number: str | None = None
    reference: str | None = None
    # Set when a recurring schedule made it.
    recurring_invoice_id: uuid.UUID | None = None
    items: list[InvoiceItemOut]
    created_by: uuid.UUID | None = None  # shown in the app, never printed
    created_at: datetime
    updated_at: datetime


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # "schedule:<days from due date>" for automatic reminders,
    # "manual:<timestamp>" for ones sent with POST /invoices/{id}/remind.
    reminder_type: str
    sent_at: datetime


class RemindersQueued(BaseModel):
    queued: int
