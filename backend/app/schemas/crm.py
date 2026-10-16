import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import INDUSTRIES, ActivityType, DealStage

# ---------- Contacts ----------


class ContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=120)
    is_primary: bool = False


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=120)
    is_primary: bool | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    first_name: str
    last_name: str | None
    email: str | None
    phone: str | None
    job_title: str | None
    is_primary: bool
    created_at: datetime


# ---------- Deals ----------


Industry = Literal[INDUSTRIES]


# A deal's importance to the business.
Priority = Literal["high", "medium", "low"]


class DealCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    customer_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    stage: DealStage = DealStage.LEAD
    value: Decimal = Field(default=Decimal("0"), ge=0)
    expected_close_date: date | None = None
    industry: Industry | None = None
    priority: Priority = "medium"
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    stage: DealStage | None = None
    value: Decimal | None = Field(default=None, ge=0)
    expected_close_date: date | None = None
    lost_reason: str | None = Field(default=None, max_length=255)
    industry: Industry | None = None
    priority: Priority | None = None
    custom_fields: dict[str, Any] | None = None


class NextActivity(BaseModel):
    id: uuid.UUID
    type: ActivityType
    subject: str
    due_date: date


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    customer_id: uuid.UUID
    contact_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    stage: DealStage
    value: Decimal
    expected_close_date: date | None
    closed_at: datetime | None
    lost_reason: str | None
    industry: str | None = None
    priority: Priority = "medium"
    custom_fields: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    # Earliest open activity: drives the board's overdue/today/none
    # indicators (Pipedrive's "next activity"). Filled in by DealService.
    next_activity: NextActivity | None = None
    # Lead-to-client milestones reached, from real activity: lead,
    # contacted, qualified, quote_sent, negotiation, won.
    milestones: list[str] = []


# ---------- Activities ----------


class ActivityCreate(BaseModel):
    type: ActivityType = ActivityType.TASK
    subject: str = Field(min_length=1, max_length=255)
    note: str | None = None
    due_date: date
    due_time: time | None = None
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class ActivityUpdate(BaseModel):
    type: ActivityType | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    note: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    done: bool | None = None
    owner_id: uuid.UUID | None = None


TaskStatus = Literal["todo", "in_progress", "blocked", "done"]


class TaskUpdateCreate(BaseModel):
    """What the person did: a new status, a note, or both. Done and
    Blocked need a note (checked in ActivityService.add_update)."""

    status: TaskStatus | None = None
    note: str | None = Field(default=None, max_length=2000)


class TaskUpdateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID | None
    status: str | None
    note: str | None
    created_at: datetime


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ActivityType
    subject: str
    note: str | None
    due_date: date
    due_time: time | None
    done: bool
    done_at: datetime | None
    status: str = "todo"
    customer_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_by: uuid.UUID | None = None
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_id: uuid.UUID
    filename: str
    content_type: str
    size: int
    uploaded_by: uuid.UUID | None
    created_at: datetime


# ---------- Notes ----------


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    customer_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    author_id: uuid.UUID | None
    created_at: datetime


# ---------- Timeline & search ----------

TimelineKind = Literal[
    "note",
    "activity",
    "deal_created",
    "deal_closed",
    "quote",
    "invoice",
    "payment",
    "reminder",
    "message",
]


class TimelineItem(BaseModel):
    """One entry in a customer's or deal's chronological history. A flat,
    display-ready shape: the client renders every kind the same way and
    links through `ref_id` by `kind`."""

    kind: TimelineKind
    at: datetime
    title: str  # English, for API consumers; the app builds its own from params
    detail: str | None = None
    ref_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    # Structured pieces of the title/detail (number, status, amount, ...) so
    # clients can phrase the entry in the user's language.
    params: dict[str, str] = {}


class SearchHit(BaseModel):
    kind: Literal["customer", "contact", "deal", "invoice", "quote"]
    id: uuid.UUID
    title: str
    subtitle: str | None = None
    # Where to open it: the customer for a contact, the record itself otherwise.
    target_id: uuid.UUID


class UserBrief(BaseModel):
    """Who can own deals and activities: name only, for pickers."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
