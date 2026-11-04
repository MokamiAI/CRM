import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.recurring import Frequency

CostStatus = Literal["due", "paid"]


def _clean_category(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    if not value:
        raise ValueError("Choose a category")
    return value[:60]


class CostCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=60)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    due_date: date
    # Paid already (a purchase made today) or still to pay (a bill).
    paid: bool = False
    paid_date: date | None = None
    supplier_id: uuid.UUID | None = None
    notes: str | None = None

    _category = field_validator("category")(_clean_category)


class CostUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    due_date: date | None = None
    paid_date: date | None = None  # only for a cost that's paid
    supplier_id: uuid.UUID | None = None
    notes: str | None = None

    _category = field_validator("category")(_clean_category)


class CostPaid(BaseModel):
    paid_date: date | None = None


class CostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    category: str
    amount: Decimal
    due_date: date
    status: CostStatus
    paid_date: date | None
    supplier_id: uuid.UUID | None
    purchase_order_id: uuid.UUID | None
    recurring_cost_id: uuid.UUID | None
    notes: str | None
    receipt_name: str | None
    receipt_size: int | None
    created_at: datetime


class CostList(BaseModel):
    items: list[CostOut]
    # Over the whole filter, not just this page.
    total_paid: Decimal
    total_due: Decimal


class CostFromPurchaseOrder(BaseModel):
    category: str = Field(default="stock", min_length=1, max_length=60)
    paid: bool = True
    paid_date: date | None = None

    _category = field_validator("category")(_clean_category)


class RecurringCostCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=60)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    frequency: Frequency = "monthly"
    start_date: date
    end_date: date | None = None
    supplier_id: uuid.UUID | None = None
    notes: str | None = None

    _category = field_validator("category")(_clean_category)

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date must be on or after the start date")
        return self


class RecurringCostUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    frequency: Frequency | None = None
    next_run_date: date | None = None
    end_date: date | None = None
    supplier_id: uuid.UUID | None = None
    notes: str | None = None

    _category = field_validator("category")(_clean_category)


class RecurringCostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    category: str
    amount: Decimal
    frequency: Frequency
    start_date: date
    next_run_date: date
    end_date: date | None
    supplier_id: uuid.UUID | None
    notes: str | None
    active: bool


class MoneySummary(BaseModel):
    """One month, counted when money moved: in = payments received, out =
    costs paid. Still to come in / still to pay are shown beside it."""

    month: str  # YYYY-MM
    money_in: Decimal
    money_out: Decimal
    profit: Decimal
    margin: Decimal | None  # profit as a % of money in; none without money in
    to_pay: Decimal  # bills not yet paid, all dates
    overdue: int  # bills past their due date
    upcoming: list[CostOut]  # due in the next 30 days (and overdue), soonest first


class MoneyMonth(BaseModel):
    month: date  # its first day
    money_in: Decimal
    money_out: Decimal
    profit: Decimal


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int


class MoneyOverview(BaseModel):
    """The last 12 months, counted when money moved."""

    months: list[MoneyMonth]
    money_in: Decimal
    money_out: Decimal
    profit: Decimal
    margin: Decimal | None
    by_category: list[CategoryTotal]  # the 12 months
    by_category_this_month: list[CategoryTotal]
    to_come_in: Decimal  # invoices not yet paid
    overdue_in: Decimal
    to_pay: Decimal  # bills not yet paid
    overdue_out: Decimal
