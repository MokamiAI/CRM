import uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator


class MilestoneUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "confirmed"] | None = None
    summary: str | None = Field(default=None, max_length=5000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    confirmed_on: date | None = None


class EvidenceCreate(BaseModel):
    kind: Literal["note", "activity", "message", "quote", "attachment", "link"]
    ref_id: uuid.UUID | None = None
    url: HttpUrl | None = Field(default=None, max_length=2000)
    explanation: str = Field(min_length=5, max_length=5000)
    occurred_on: date
    contact_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def source(self):
        if not self.explanation.strip() or (self.kind == "link" and (not self.url or self.ref_id)) or (self.kind != "link" and (not self.ref_id or self.url)):
            raise ValueError("Choose one existing record or an agreed-document link")
        return self


class JourneyUpdate(BaseModel):
    qualification_reason: str | None = Field(default=None, max_length=5000)
    decision_process: str | None = Field(default=None, max_length=5000)
    assumptions: str | None = Field(default=None, max_length=5000)
    scope: str | None = Field(default=None, max_length=10000)
    commitments: str | None = Field(default=None, max_length=5000)
    dependencies: str | None = Field(default=None, max_length=5000)
    risks: str | None = Field(default=None, max_length=5000)
    success_measure: str | None = Field(default=None, max_length=5000)
    baseline: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    target: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    actual: Decimal | None = Field(default=None, max_digits=18, decimal_places=4)
    unit: str | None = Field(default=None, max_length=80)
    delivery_owner_id: uuid.UUID | None = None
    account_owner_id: uuid.UUID | None = None
    next_review_date: date | None = None
    recurring: bool | None = None
    renewal_date: date | None = None


class ExpansionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    value: Decimal = Field(default=0, ge=0, max_digits=12, decimal_places=2)
