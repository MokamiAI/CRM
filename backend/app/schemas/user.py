import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import SUPPORTED_LANGUAGES, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    # Left out: they're invited by email and choose their own password.
    password: str | None = Field(default=None, min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.STAFF


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


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
