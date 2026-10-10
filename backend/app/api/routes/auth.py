from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.database import CommitBeforeResponseRoute
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.user import ProfileUpdate, UserOut
from app.services.auth_service import AuthService
from app.services.email_service import clean_signature

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).login(data.email, data.password)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Sign up a new company; the person signing up becomes its admin."""
    return await AuthService(db).register(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: LogoutRequest, db: AsyncSession = Depends(get_db)):
    await AuthService(db).logout(data.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserOut)
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
    return current_user
