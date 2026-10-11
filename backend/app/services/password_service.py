"""Forgot password: a one-time link, valid for an hour, emailed to the
account. The reply never says whether an email has an account."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.core.tenancy import set_system
from app.models.platform import PasswordReset
from app.models.user import RefreshToken, User
from app.repositories.user_repository import UserRepository
from app.services import platform_email

TOKEN_LIFETIME = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordService:
    def __init__(self, db: AsyncSession):
        self.db = db
        set_system(db)  # before sign-in: look the account up across companies

    async def request_reset(self, email: str) -> None:
        user = await UserRepository(self.db).get_by_email(email)
        if user is None or not user.is_active:
            return
        token = secrets.token_urlsafe(32)
        self.db.add(PasswordReset(user_id=user.id, token_hash=_hash(token), expires_at=datetime.now(timezone.utc) + TOKEN_LIFETIME))
        await self.db.flush()
        await platform_email.queue(
            self.db,
            platform_email.compose(
                to=user.email,
                subject="Reset your YGT password",
                title="Reset your password",
                paragraphs=[
                    f"Hi {user.full_name.split(' ')[0]},",
                    "Someone asked to reset the password for your YGT account. If it was you, use the button below. The link works once and expires in an hour.",
                    "If it wasn't you, you can ignore this email; your password stays the same.",
                ],
                button=("Choose a new password", platform_email.app_link(f"/reset-password?token={token}")),
            ),
        )

    async def reset(self, token: str, password: str) -> None:
        now = datetime.now(timezone.utc)
        row = await self.db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash(token)).with_for_update())
        if row is None or row.used_at is not None or row.expires_at < now:
            raise AppError("This reset link has expired or was already used. Ask for a new one.", "RESET_LINK_INVALID")
        user = await self.db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise AppError("This reset link has expired or was already used. Ask for a new one.", "RESET_LINK_INVALID")
        user.password_hash = hash_password(password)
        row.used_at = now
        # Signed out everywhere: old sessions can't carry on with the old password.
        await self.db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        await self.db.flush()
