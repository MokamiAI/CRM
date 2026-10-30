from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Self-service sign-up: a new company and its first admin."""

    company_name: str = Field(min_length=1, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # The plan they're trying (free for the trial; chosen again at checkout).
    plan: Literal["hustle", "grow", "scale"] = "grow"
    # Optional: the year's revenue goal, for the dashboard's goal card.
    annual_revenue_goal: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    # Where the business is: saved as the company's address (on its documents).
    business_address: str = Field(min_length=10, max_length=500)
    # Ticked (never by default): YGT may send them tips, news and offers.
    marketing_opt_in: bool = False
    # Required: they agree to the terms and privacy policy (recorded).
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("accept_terms")
    @classmethod
    def _terms_accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Agree to the terms and privacy policy to create an account")
        return value

    @field_validator("business_address")
    @classmethod
    def _real_address(cls, value: str) -> str:
        value = value.strip()
        # A street or place and a town, at least: two words with letters in.
        words = [w for w in value.replace(",", " ").split() if any(ch.isalpha() for ch in w)]
        if len(value) < 10 or len(words) < 2:
            raise ValueError("Enter the business's street address and town")
        return value
