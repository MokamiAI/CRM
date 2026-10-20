import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class MeetingDraft(BaseModel):
    attendee_name: str | None = Field(default=None, max_length=241)
    attendee_email: EmailStr | None = None
    duration_minutes: int = Field(default=30, ge=15, le=480)
    location: str | None = Field(default=None, max_length=500)
    send_invitation: bool = True


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    activity_id: uuid.UUID
    organizer_id: uuid.UUID
    attendee_name: str
    attendee_email: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    location: str | None
    status: str
    sequence: int
    response_reason: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None


class MeetingReview(BaseModel):
    accept: bool
    reason: str | None = Field(default=None, max_length=2000)


class MeetingContactOut(BaseModel):
    contact_id: uuid.UUID | None = None
    name: str = ""
    email: str = ""


class CalendarBlock(BaseModel):
    activity_id: uuid.UUID
    subject: str
    starts_at: datetime
    ends_at: datetime
    status: str
    proposed: bool = False
    attendee_name: str | None = None
