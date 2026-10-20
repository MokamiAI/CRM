import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TicketCategory = Literal["question", "problem", "billing", "feature", "account"]
TicketStatus = Literal["open", "in_progress", "waiting", "resolved", "closed"]
Urgency = Literal["low", "normal", "high"]


# ---------- Help desk ----------


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    category: TicketCategory = "question"
    urgency: Urgency = "normal"
    body: str = Field(min_length=5, max_length=10_000)


class TicketReply(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class AdminTicketReply(TicketReply):
    internal: bool = False  # a note for YGT's team only


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    urgency: Urgency | None = None
    assigned_to: str | None = Field(default=None, max_length=255)


class TicketMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    author_name: str
    from_platform: bool
    internal: bool
    body: str


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    subject: str
    category: str
    urgency: str
    status: str
    priority_plan: bool
    last_message_at: datetime
    last_from_platform: bool
    created_at: datetime
    closed_at: datetime | None


class TicketAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    content_type: str
    size: int


class TicketTemplate(BaseModel):
    key: str = Field(pattern=r"^[a-z_]{1,40}$")
    name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=5, max_length=10000)


class TicketDetail(TicketOut):
    messages: list[TicketMessageOut]
    attachments: list[TicketAttachmentOut] = Field(default_factory=list)


class AdminTicketOut(TicketOut):
    company_id: uuid.UUID
    company_name: str
    created_by_name: str | None = None
    created_by_email: str | None = None
    assigned_to: str | None = None
    plan: str | None = None


class AdminTicketDetail(AdminTicketOut):
    messages: list[TicketMessageOut]
    attachments: list[TicketAttachmentOut] = Field(default_factory=list)


# ---------- Sessions ----------


SessionTopic = Literal["onboarding", "training", "support", "billing", "other"]


class SlotDay(BaseModel):
    date: date
    slots: list[datetime]


class SlotsOut(BaseModel):
    host_name: str = "Johannes"
    host_email: str = "johannes@yougt.co.za"
    timezone: str
    slot_minutes: int
    days: list[SlotDay]


class BookingCreate(BaseModel):
    starts_at: datetime
    topic: SessionTopic = "onboarding"
    notes: str | None = Field(default=None, max_length=2000)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    topic: str
    notes: str | None
    status: str
    attendee_name: str
    attendee_email: str


class AdminBookingOut(BookingOut):
    company_id: uuid.UUID
    company_name: str


class Availability(BaseModel):
    """When sessions can be booked, in the admin's time zone."""

    timezone: str = "Africa/Johannesburg"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # Monday = 0
    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="16:00", pattern=r"^\d{2}:\d{2}$")
    slot_minutes: int = Field(default=30, ge=15, le=180)
    min_notice_hours: int = Field(default=24, ge=0, le=720)
    days_ahead: int = Field(default=21, ge=1, le=90)
    blocked_dates: list[date] = Field(default_factory=list)
    meeting_link: str | None = Field(default=None, max_length=300)  # e.g. a Google Meet or Teams link
    enabled: bool = True


# ---------- Contact us ----------


class ContactCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    topic: Literal["sales", "support", "billing", "partnership", "other"] = "sales"
    message: str = Field(min_length=5, max_length=5000)
    # Honeypot: hidden from people; bots fill it in.
    website: str | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    name: str
    email: str
    phone: str | None
    company: str | None
    topic: str
    message: str
    status: str
    admin_notes: str | None


class ContactUpdate(BaseModel):
    status: Literal["new", "contacted", "closed"] | None = None
    admin_notes: str | None = Field(default=None, max_length=5000)


# ---------- Passwords ----------


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


# ---------- Admin ----------


class SuspendIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class DeleteCompanyIn(BaseModel):
    # The company's name, typed out: a deliberate step, not a stray click.
    confirm_name: str = Field(min_length=1, max_length=255)


class ExtendTrialIn(BaseModel):
    days: int = Field(ge=1, le=90)


class RefundIn(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)  # None: the full payment
    reason: str = Field(min_length=3, max_length=300)
