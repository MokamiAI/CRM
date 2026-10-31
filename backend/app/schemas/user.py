import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import SUPPORTED_LANGUAGES, UserRole

# Team chat colours a person can pick (the app maps each to soft tints).
CHAT_COLORS = ("indigo", "violet", "teal", "emerald", "amber", "orange", "fuchsia", "cyan", "sky", "lime")


class UserCreate(BaseModel):
    email: EmailStr
    # Left out: they're invited by email and choose their own password.
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.STAFF
    job_title: str | None = Field(default=None, max_length=100)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    # Empty string clears it.
    job_title: str | None = Field(default=None, max_length=100)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    language: str
    tour_completed_at: datetime | None = None
    email_signature: str | None = None
    # Clicked the link we emailed; until then the app shows a reminder.
    email_verified_at: datetime | None = None
    # YGT's own team: may open the admin site.
    is_platform_admin: bool = False
    # Invited but hasn't chosen a password yet.
    invite_pending: bool = False
    # YGT's own marketing: None until they've answered.
    marketing_opt_in: bool | None = None
    chat_color: str | None = None
    job_title: str | None = None
    quote_seen: str | None = None
    created_at: datetime


class MeOut(UserOut):
    # The company is suspended: the app shows a notice instead of the screens.
    account_suspended: bool = False
    suspended_reason: str | None = None
    # Unconfirmed email: access ends at this time unless the link is clicked.
    verify_by: datetime | None = None


class ProfileUpdate(BaseModel):
    """What any signed-in user may change about themselves."""

    language: Literal[SUPPORTED_LANGUAGES] | None = None  # type: ignore[valid-type]
    # True marks the guided tour done; False brings it back ("take the tour again").
    tour_completed: bool | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    # Empty string clears it.
    email_signature: str | None = Field(default=None, max_length=1000)
    # YGT's tips, news and offers: yes or no, answered in the app's
    # one-time question (prompt) or in Settings.
    marketing_opt_in: bool | None = None
    marketing_source: Literal["prompt", "settings"] = "settings"
    # Their team chat colour; None goes back to the one picked for them.
    chat_color: Literal[CHAT_COLORS] | None = None  # type: ignore[valid-type]
    # Their position; empty string clears it.
    job_title: str | None = Field(default=None, max_length=100)
    # The sales quote of the week they've seen.
    quote_seen: str | None = Field(default=None, max_length=20)
