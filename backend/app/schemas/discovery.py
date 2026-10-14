import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.crm import Industry


class DiscoverySettingsIn(BaseModel):
    enabled: bool = True
    area: str | None = Field(default=None, max_length=200)
    radius_km: int = Field(default=10, ge=1, le=50)
    industries: list[Industry] = Field(default_factory=list, max_length=8)


class DiscoverySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    area: str | None
    located: bool = False
    radius_km: int
    industries: list[str]
    last_run_at: datetime | None
    nearby_status: str | None = None
    nearby_checked_at: datetime | None = None


class DiscoveredLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    status: str
    name: str
    industry: str | None
    kind: str | None
    address: str | None
    phone: str | None
    email: str | None
    website: str | None
    details: dict[str, Any]
    last_contact: date | None
    customer_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    created_at: datetime


class DiscoveryRunOut(BaseModel):
    found: int  # from the company's own records
    looking_nearby: bool = False  # the map lookup carries on after this answer


class AddLeadIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
