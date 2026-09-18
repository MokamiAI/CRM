from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(subject=str(user.id), role=user.role.value)
        raw_refresh, refresh_hash, expires_at = generate_refresh_token()
        await self.refresh_tokens.create(
            RefreshToken(user_id=user.id, token_hash=refresh_hash, expires_at=expires_at)
        )
        return TokenResponse(access_token=access_token, refresh_token=raw_refresh)

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Incorrect email or password")
        return await self._issue_tokens(user)

    async def refresh(self, raw_refresh_token: str) -> TokenResponse:
        token_hash = hash_refresh_token(raw_refresh_token)
        token = await self.refresh_tokens.get_by_hash(token_hash)
        if token is None or token.revoked_at is not None:
            raise UnauthorizedError("Refresh token is invalid or has been revoked")
        if token.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token has expired")

        user = await self.users.get_by_id(token.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Account is no longer active")

        # Rotate: revoke the used token and issue a fresh pair so a stolen
        # refresh token can only be replayed once before detection.
        await self.refresh_tokens.revoke(token)
        return await self._issue_tokens(user)

    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        token = await self.refresh_tokens.get_by_hash(token_hash)
        if token is not None and token.revoked_at is None:
            await self.refresh_tokens.revoke(token)
