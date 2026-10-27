"""Deleting your own account (Settings, or My profile): app stores require
that anyone who can sign up can also remove their account and its data.

The only admin of a company takes the company with them: every customer,
invoice and file is erased (they type the company's name to confirm), and a
card subscription is stopped first. Anyone else leaves the company: their
name, email and password are erased and they can't sign in again; what they
did for the company (quotes sent, notes) stays with the company, under
"Deleted user". YGT's own admins can't delete themselves here."""
import logging
import secrets

from sqlalchemy import delete, func, select, update

from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password
from app.core.tenancy import set_system
from app.models.company_settings import CompanySettings
from app.models.enums import UserRole
from app.models.notification import PushSubscription
from app.models.user import RefreshToken, User
from app.services.admin_service import erase_company

logger = logging.getLogger(__name__)


async def is_last_admin(db, user: User) -> bool:
    if user.role != UserRole.ADMIN:
        return False
    others = await db.scalar(select(func.count()).select_from(User).where(
        User.company_id == user.company_id, User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != user.id))
    return not others


async def delete_own_account(db, user: User, password: str, company_name: str | None) -> str:
    """Returns "company" when the whole company went, else "account"."""
    if not verify_password(password, user.password_hash):
        raise AppError("That password isn't right.", "PASSWORD_INCORRECT", 400)
    if user.is_platform_admin:
        raise AppError("YGT's own admins can't delete their account here.", "PLATFORM_ADMIN_DELETE", 409)
    set_system(db)
    if await is_last_admin(db, user):
        company = await db.get(CompanySettings, user.company_id)
        if (company_name or "").strip().lower() != company.company_name.strip().lower():
            raise AppError("Type your company's name exactly as shown to confirm.", "COMPANY_NAME_MISMATCH", 400)
        counts = await erase_company(db, company)
        logger.warning("Company %s (%s) deleted by its own admin: %s", company.company_name, company.id, counts)
        return "company"

    user_id = user.id
    user.email = f"deleted-{user_id.hex}@deleted.invalid"
    user.full_name = "Deleted user"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.email_signature = None
    user.is_active = False
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                     .values(revoked_at=func.now()))
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id))
    await db.flush()
    logger.warning("User %s deleted their account", user_id)
    return "account"
