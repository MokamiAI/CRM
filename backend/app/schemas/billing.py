import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanOut(BaseModel):
    key: str
    name: str
    monthly_cents: int
    annual_cents: int  # per company, or per user when per_user
    per_user: bool
    min_users: int
    max_users: int | None
    max_customers: int | None
    invoices_per_month: int | None
    features: list[str]


class Usage(BaseModel):
    users: int
    customers: int
    invoices_this_month: int


class Limits(BaseModel):
    users: int | None
    customers: int | None
    invoices_this_month: int | None


class BillingOut(BaseModel):
    plan: str  # what the company can use right now
    state: str  # trialing | active | past_due | cancelled | trial_ended | lapsed | free
    subscribed_plan: str | None  # what they pay for (may differ from plan once lapsed)
    interval: str
    seats: int
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    features: list[str]
    usage: Usage
    limits: Limits
    has_card: bool
    payments_enabled: bool  # Paystack keys are set on this server


class CheckoutIn(BaseModel):
    plan: Literal["hustle", "grow", "scale"]
    interval: Literal["monthly", "annually"] = "monthly"
    users: int = Field(default=1, ge=1, le=500)


class CheckoutOut(BaseModel):
    authorization_url: str


class ConfirmIn(BaseModel):
    reference: str = Field(min_length=4, max_length=100)


class ConfirmOut(BaseModel):
    confirmed: bool
    billing: BillingOut


class LinkOut(BaseModel):
    url: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    amount_cents: int
    currency: str
    plan: str
    interval: str
    seats: int
    paid_at: datetime
