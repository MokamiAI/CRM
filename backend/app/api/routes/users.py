import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_room, require_role
from app.core.exceptions import ConflictError
from app.models.user import User
from app.services.invite_service import InviteService
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.billing_service import BillingService
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.user_service import UserService
from app.services.verification_service import VerificationService

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/users", tags=["users"], dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.post("", response_model=UserOut, status_code=201, dependencies=[Depends(plan_room("users"))])
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_user)):
    """Adds a person. Without a password they're invited by email and
    choose their own; with one (older flow), they're asked to confirm."""
    user = await UserService(db).create_user(data)
    company = await CompanySettingsRepository(db).get_current()
    if data.password:
        await VerificationService(db).send(user, company_name=company.company_name)
    else:
        await InviteService(db).send(user, admin, company.company_name)
    await db.refresh(user)
    return user


@router.post("/{user_id}/invite", response_model=UserOut)
async def resend_invite(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_user)):
    """A fresh invitation link, for someone who hasn't joined yet."""
    user = await UserService(db).get_user(user_id)
    if not user.invite_pending:
        raise ConflictError("This person has already joined", "INVITE_ALREADY_ACCEPTED")
    company = await CompanySettingsRepository(db).get_current()
    await InviteService(db).send(user, admin, company.company_name)
    await db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return await UserService(db).list_users(offset=offset, limit=limit)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await UserService(db).get_user(user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: uuid.UUID, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    service = UserService(db)
    if data.is_active and not (await service.get_user(user_id)).is_active:
        await BillingService(db).check_room("users")  # reactivating takes a seat
    return await service.update_user(user_id, data)
