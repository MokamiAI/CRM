from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.models.enums import UserRole
from app.schemas.company_settings import CompanySettingsOut, CompanySettingsUpdate
from app.services.company_settings_service import CompanySettingsService

router = APIRouter(
    prefix="/settings", tags=["settings"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("", response_model=CompanySettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    row = await CompanySettingsService(db).get_settings()
    return CompanySettingsOut.from_model(row)


@router.patch("", response_model=CompanySettingsOut)
async def update_settings(data: CompanySettingsUpdate, db: AsyncSession = Depends(get_db)):
    row = await CompanySettingsService(db).update_settings(data)
    return CompanySettingsOut.from_model(row)
