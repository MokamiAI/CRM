import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError, UnauthorizedError
from app.core.tenancy import set_system, set_tenant
from app.core.security import decode_token
from app.models.company_settings import CompanySettings
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.billing_service import BillingService
from app.services.verification_service import verification_overdue

__all__ = ["get_db", "get_current_user", "require_role"]

_bearer_scheme = HTTPBearer(auto_error=False)


_READ_ONLY = {"GET", "HEAD", "OPTIONS"}
# Still usable after a trial or plan ends: choosing and paying for a plan,
# the person's own profile and sign-out, and asking YGT for help.
_ALWAYS_OPEN = ("/billing", "/auth/", "/support", "/bookings", "/admin")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing authentication credentials")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired access token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired access token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid or expired access token")

    # The token names a user, not a company: find them across companies,
    # then scope everything else in this request to their company.
    set_system(db)
    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is no longer active")
    set_tenant(db, user.company_id)
    # For the activity and error logs (app/core/middleware.py).
    request.state.user_id = str(user.id)
    request.state.company_id = str(user.company_id)
    request.state.actor_email = user.email
    path = request.url.path.removeprefix(settings.API_V1_PREFIX)
    # Email still not confirmed 48 hours on: only signing in/out, "who am I"
    # and resending the link work until the address is proven.
    if verification_overdue(user) and not path.startswith("/auth/"):
        raise PermissionDeniedError("Please confirm your email address to keep using YGT. We've sent you a link.", "EMAIL_NOT_VERIFIED")
    if not user.is_platform_admin and not path.startswith("/auth/"):
        company = await db.get(CompanySettings, user.company_id)
        if company is not None and company.suspended_at is not None:
            raise PermissionDeniedError("This account has been suspended. Please contact YGT support.", "ACCOUNT_SUSPENDED")
    if request.method not in _READ_ONLY and not path.startswith(_ALWAYS_OPEN):
        await BillingService(db).ensure_active()
    return user


def plan_feature(feature: str):
    """The company's plan must include this feature (see app/core/plans.py)."""

    async def _check(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        await BillingService(db).require_feature(feature)
        return user

    return _check


def plan_room(what: str):
    """The company's plan must have room for one more of these:
    users, customers or invoices_this_month."""

    async def _check(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
        await BillingService(db).check_room(what)
        return user

    return _check


def require_role(*allowed_roles: UserRole):
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise PermissionDeniedError()
        return user

    return _check


async def require_platform_admin(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    """YGT's own team only (PLATFORM_ADMIN_EMAILS). Admin queries then run
    across every company."""
    if not user.is_platform_admin:
        raise PermissionDeniedError("YGT team only", "NOT_PLATFORM_ADMIN")
    set_system(db)
    return user
