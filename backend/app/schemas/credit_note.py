import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreditNoteCreate(BaseModel):
    """Take an amount off an invoice that has gone out: an amount including
    VAT, or everything not yet credited ("rest"). The VAT is split the way
    the invoice's own VAT is, so the credit note's VAT matches it."""

    kind: Literal["amount", "rest"] = "amount"
    value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    # Why, printed on the credit note: "Discount agreed", "Returned 2 chairs".
    reason: str = Field(min_length=2, max_length=500)
    issue_date: date | None = None

    @model_validator(mode="after")
    def _value_needed(self):
        if self.kind == "amount" and self.value is None:
            raise ValueError("value is needed for an amount")
        self.reason = self.reason.strip()
        if len(self.reason) < 2:
            raise ValueError("a reason is needed")
        return self


class CreditNoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    details: str | None = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal
    sort_order: int


class CreditNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    credit_note_number: str
    invoice_id: uuid.UUID
    invoice_number: str | None = None
    customer_id: uuid.UUID
    status: Literal["issued", "void"]
    issue_date: date
    reason: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    items: list[CreditNoteItemOut]
    created_by: uuid.UUID | None = None
    created_at: datetime
    voided_at: datetime | None = None
