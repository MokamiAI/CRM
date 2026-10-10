import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StageTotal(BaseModel):
    stage: str
    count: int
    value: Decimal


class WonTotal(BaseModel):
    count: int
    value: Decimal


class MonthTotal(BaseModel):
    month: str  # first day of the month, ISO date
    total: Decimal


class TopDeal(BaseModel):
    id: uuid.UUID
    title: str
    customer_id: uuid.UUID
    customer_name: str
    stage: str
    value: Decimal
    owner_id: uuid.UUID | None


class FeedItem(BaseModel):
    kind: str
    at: datetime
    title: str
    detail: str | None = None
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    deal_id: uuid.UUID | None = None
    invoice_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    params: dict[str, str] = {}  # see TimelineItem.params


class ReportSummary(BaseModel):
    pipeline: list[StageTotal]
    open_pipeline_value: Decimal
    open_deal_count: int
    won_this_month: WonTotal
    win_rate: float | None  # won / (won + lost), last 90 days
    avg_won_deal: Decimal | None
    outstanding: Decimal
    overdue: Decimal
    open_invoice_count: int
    collected_by_month: list[MonthTotal]
    top_deals: list[TopDeal]
    recent_activity: list[FeedItem]


class CustomerOverview(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    is_active: bool
    primary_contact: str | None
    open_deals: int
    pipeline_value: Decimal
    balance: Decimal
    overdue_invoices: int
    last_activity_at: datetime | None
