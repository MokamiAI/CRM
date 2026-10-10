import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# ---------- Audience rules ----------
# A customer is in a segment when they match every rule.


class CustomFieldRule(BaseModel):
    kind: Literal["custom_field"]
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(max_length=200)


class DaysRule(BaseModel):
    # bought_within_days: has a (non-draft, non-void) invoice issued in the last N days
    # no_purchase_days:   has no such invoice in the last N days (win-back)
    # created_within_days: became a customer in the last N days
    kind: Literal["bought_within_days", "no_purchase_days", "created_within_days"]
    days: int = Field(ge=1, le=3650)


class FlagRule(BaseModel):
    # has_open_balance: owes money on a sent/partly paid/overdue invoice
    # has_open_deal:    has a deal that is still in the pipeline
    kind: Literal["has_open_balance", "has_open_deal"]
    value: bool = True


Rule = Annotated[CustomFieldRule | DaysRule | FlagRule, Field(discriminator="kind")]


class SegmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rules: list[Rule] = Field(default_factory=list, max_length=20)


class SegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rules: list[dict]
    created_at: datetime


class AudiencePreview(BaseModel):
    count: int
    # A few names so the user can sanity-check who they're about to email.
    sample: list[str]


class AudienceQuery(BaseModel):
    rules: list[Rule] = Field(default_factory=list, max_length=20)


# ---------- Campaigns ----------


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    subject: str = Field(default="", max_length=200)
    preheader: str | None = Field(default=None, max_length=200)
    body: str = Field(default="", max_length=20_000)
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    cta_text: str | None = Field(default=None, max_length=60)
    cta_url: HttpUrl | None = None
    segment_id: uuid.UUID | None = None


class CampaignSchedule(BaseModel):
    # None means send right away.
    scheduled_at: datetime | None = None


class CampaignStats(BaseModel):
    recipients: int = 0
    sent: int = 0
    failed: int = 0
    opened: int = 0
    unsubscribed: int = 0


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    subject: str
    preheader: str | None
    body: str
    product_ids: list[uuid.UUID]
    cta_text: str | None
    cta_url: str | None
    segment_id: uuid.UUID | None
    status: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    stats: CampaignStats = CampaignStats()


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None = None
    email: str
    status: str
    error: str | None
    sent_at: datetime | None
    opened_at: datetime | None
    unsubscribed_at: datetime | None


class PreviewOut(BaseModel):
    subject: str
    html: str


class FeaturedProduct(BaseModel):
    """A product as it appears in a campaign email."""

    name: str
    description: str | None
    image_url: str | None
    price: Decimal
    special_price: Decimal | None
    special_until: date | None
