"""Inviting a team member: the admin gives a name, email and role; the
person gets an email with a one-time link, opens it, chooses their own
password (typed twice) and is signed in. Opening the link proves the
inbox is theirs, so their email counts as confirmed.

The link is a PasswordReset row (hashed token, single use), valid for
INVITE_LIFETIME; "Resend invite" makes a fresh one."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.legal import TERMS_VERSION
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.core.tenancy import set_system
from app.models.company_settings import CompanySettings
from app.models.platform import PasswordReset
from app.models.user import User
from app.services import platform_email

logger = logging.getLogger(__name__)

INVITE_LIFETIME = timedelta(days=7)
_INVALID = "This invitation link has expired or was already used. Ask your admin to send a new one."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def unusable_password() -> str:
    """A password nobody knows: the account can't be signed into until the
    invitation is accepted."""
    return hash_password(secrets.token_urlsafe(32))


class InviteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def send(self, user: User, invited_by: User | None, company_name: str) -> None:
        """Emails the invitation (commits)."""
        token = secrets.token_urlsafe(32)
        self.db.add(PasswordReset(user_id=user.id, token_hash=_hash(token), expires_at=datetime.now(timezone.utc) + INVITE_LIFETIME))
        user.invited_at = datetime.now(timezone.utc)
        await self.db.flush()
        who = invited_by.full_name if invited_by else company_name
        if settings.REDIS_URL.startswith("memory") and settings.ENVIRONMENT != "production":
            # Working locally, emails aren't delivered: the link is in the log.
            logger.warning("Invitation link for %s (local only): %s", user.email, platform_email.app_link(f"/invite?token={token}"))
        await platform_email.queue(
            self.db,
            platform_email.compose(
                to=user.email,
                subject=f"{who} invited you to {company_name} on YGT",
                title=f"Join {company_name} on YGT",
                paragraphs=[
                    f"Hi {user.full_name.split(' ')[0]},",
                    f"{who} has added you to {company_name}'s team on YGT, where they keep their customers, quotes, invoices and tasks.",
                    "Use the button to create your password and sign in. The link works once and expires in 7 days.",
                    "If you weren't expecting this, you can ignore this email.",
                ],
                button=("Create my password", platform_email.app_link(f"/invite?token={token}")),
            ),
        )

    async def _row(self, token: str, lock: bool = False) -> tuple[PasswordReset, User]:
        set_system(self.db)  # signed out: find the invitation across companies
        stmt = select(PasswordReset).where(PasswordReset.token_hash == _hash(token))
        row = await self.db.scalar(stmt.with_for_update() if lock else stmt)
        if row is None or row.used_at is not None or row.expires_at < datetime.now(timezone.utc):
            raise AppError(_INVALID, "INVITE_LINK_INVALID")
        user = await self.db.get(User, row.user_id)
        if user is None or not user.is_active or user.invite_accepted_at is not None or user.invited_at is None:
            raise AppError(_INVALID, "INVITE_LINK_INVALID")
        return row, user

    async def describe(self, token: str) -> dict:
        """Who the link is for, to greet them on the page."""
        _, user = await self._row(token)
        company = await self.db.get(CompanySettings, user.company_id)
        return {"full_name": user.full_name, "email": user.email, "company_name": company.company_name if company else ""}

    async def accept(self, token: str, password: str) -> User:
        """Sets their password; the link is spent; the email is confirmed."""
        row, user = await self._row(token, lock=True)
        now = datetime.now(timezone.utc)
        user.password_hash = hash_password(password)
        user.invite_accepted_at = now
        # Joining says they agree to the terms and privacy policy (shown on the page).
        user.terms_accepted_at = now
        user.terms_version = TERMS_VERSION
        if user.email_verified_at is None:
            user.email_verified_at = now
        row.used_at = now
        await self.db.flush()
        return user
