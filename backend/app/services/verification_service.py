"""Confirming that people own the email address they signed up with."""
import uuid
from datetime import datetime, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import create_email_token, decode_token
from app.core.tenancy import ALL_TENANTS, set_tenant
from app.models.user import User
from app.services import platform_email


class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send(self, user: User, company_name: str | None = None) -> None:
        """Emails the "Confirm your email" link (commits first)."""
        token = create_email_token(str(user.id), user.email)
        intro = (
            f"{company_name} has added you to YGT. Please confirm that this is your email address."
            if company_name
            else "Welcome to YGT! Please confirm that this is your email address, so we can reach you about your account."
        )
        await platform_email.queue(
            self.db,
            platform_email.compose(
                to=user.email,
                subject="Confirm your email for YGT",
                title="Confirm your email",
                paragraphs=[f"Hi {user.full_name.split(' ')[0]},", intro, "The link works for 7 days. If you didn't sign up for YGT, you can ignore this email."],
                button=("Confirm my email", platform_email.app_link(f"/verify-email?token={token}")),
            ),
        )

    async def verify(self, token: str) -> User:
        try:
            payload = decode_token(token)
            user_id = uuid.UUID(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            raise AppError("This link isn't valid any more. Sign in and ask for a new one.", "VERIFY_LINK_INVALID")
        if payload.get("type") != "verify-email":
            raise AppError("This link isn't valid any more. Sign in and ask for a new one.", "VERIFY_LINK_INVALID")
        user = await self.db.scalar(select(User).where(User.id == user_id), execution_options={ALL_TENANTS: True})
        if user is None or user.email.lower() != payload.get("email"):
            raise AppError("This link isn't valid any more. Sign in and ask for a new one.", "VERIFY_LINK_INVALID")
        if user.email_verified_at is None:
            # The link is opened signed out: act as this person's company.
            set_tenant(self.db, user.company_id)
            user.email_verified_at = datetime.now(timezone.utc)
            await self.db.flush()
        return user
