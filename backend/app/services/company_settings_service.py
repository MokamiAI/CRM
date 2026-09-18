from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_settings import CompanySettings
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.company_settings import CompanySettingsUpdate


class CompanySettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)

    async def get_settings(self) -> CompanySettings:
        return await self.company_settings.get_singleton()

    async def update_settings(self, data: CompanySettingsUpdate) -> CompanySettings:
        row = await self.company_settings.get_singleton()
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        return await self.company_settings.save(row)
