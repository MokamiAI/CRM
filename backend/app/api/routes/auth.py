from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.database import CommitBeforeResponseRoute
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.models.company_settings import CompanySettings
from app.schemas.user import MeOut, ProfileUpdate, UserOut
from app.schemas.platform import ForgotPassword, ResetPassword
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.password_service import PasswordService
from app.services.invite_service import InviteService
from app.services.verification_service import VerificationService, verify_by
from app.services.email_service import clean_signature
from app.services.account_deletion import delete_own_account, is_last_admin

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    tokens = await AuthService(db).login(data.email, data.password)
    # The activity log records the sign-in against the person's company.
    user = await UserRepository(db).get_by_email(data.email)
    request.state.actor_email = data.email
    request.state.user_id = str(user.id)
    request.state.company_id = str(user.company_id)
    return tokens


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Sign up a new company; the person signing up becomes its admin."""
    tokens = await AuthService(db).register(data)
    user = await UserRepository(db).get_by_email(data.email)
    await VerificationService(db).send(user)
    return tokens


class AcceptInvite(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


@router.get("/invite")
async def invite_details(token: str, db: AsyncSession = Depends(get_db)):
    """Who an invitation is for, to greet them on the page."""
    return await InviteService(db).describe(token)


@router.post("/invite", response_model=TokenResponse)
async def accept_invite(data: AcceptInvite, request: Request, db: AsyncSession = Depends(get_db)):
    """They chose their password: signed in, email confirmed."""
    user = await InviteService(db).accept(data.token, data.password)
    request.state.actor_email = user.email
    request.state.user_id = str(user.id)
    request.state.company_id = str(user.company_id)
    return await AuthService(db)._issue_tokens(user)


class VerifyEmail(BaseModel):
    token: str = Field(min_length=20, max_length=1000)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(data: VerifyEmail, db: AsyncSession = Depends(get_db)):
    """The link in "Confirm your email". Works signed in or not."""
    await VerificationService(db).verify(data.token)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.email_verified_at is None:
        await VerificationService(db).send(current_user)
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: LogoutRequest, db: AsyncSession = Depends(get_db)):
    await AuthService(db).logout(data.refresh_token)


async def _me_out(user: User, db: AsyncSession) -> MeOut:
    """The signed-in person, with what the app needs to know about access."""
    company = await db.get(CompanySettings, user.company_id)
    suspended = company is not None and company.suspended_at is not None and not user.is_platform_admin
    return MeOut(
        **UserOut.model_validate(user).model_dump(),
        account_suspended=suspended,
        suspended_reason=company.suspended_reason if suspended else None,
        verify_by=verify_by(user),
    )


@router.get("/me", response_model=MeOut)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _me_out(current_user, db)


# The same shape as GET /me, so saving a setting keeps what the app knows.
@router.patch("/me", response_model=MeOut)
async def update_me(
    data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-service profile settings (currently the UI language). Admin
    user management stays under /users."""
    changes = data.model_dump(exclude_unset=True)
    if "tour_completed" in changes:
        current_user.tour_completed_at = datetime.now(timezone.utc) if changes.pop("tour_completed") else None
    if "email_signature" in changes:
        changes["email_signature"] = clean_signature(changes["email_signature"])
    for field, value in changes.items():
        setattr(current_user, field, value)
    await db.flush()
    return await _me_out(current_user, db)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    """Emails a reset link if the account exists. Always the same reply,
    so nobody can use this to find out who has an account."""
    await PasswordService(db).request_reset(data.email)
    return {"ok": True}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    await PasswordService(db).reset(data.token, data.password)


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=255)


@router.get("/delete-account")
async def delete_account_check(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """What deleting would remove: just this account, or the whole company."""
    return {"whole_company": await is_last_admin(db, current_user), "allowed": not current_user.is_platform_admin}


@router.post("/delete-account")
async def delete_account(data: DeleteAccountIn, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"deleted": await delete_own_account(db, current_user, data.password, data.company_name)}
