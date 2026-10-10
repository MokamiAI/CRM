import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import SUPPORTED_LANGUAGES, UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
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
    created_at: datetime


class ProfileUpdate(BaseModel):
    """What any signed-in user may change about themselves."""

    language: Literal[SUPPORTED_LANGUAGES] | None = None  # type: ignore[valid-type]
    # True marks the guided tour done; False brings it back ("take the tour again").
    tour_completed: bool | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    # Empty string clears it.
    email_signature: str | None = Field(default=None, max_length=1000)
