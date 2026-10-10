from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt
from app.models.company_settings import CompanySettings
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.company_settings import CompanySettingsUpdate
from app.services.email_service import clean_signature


class CompanySettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)

    async def get_settings(self) -> CompanySettings:
        return await self.company_settings.get_current()

    async def update_settings(self, data: CompanySettingsUpdate) -> CompanySettings:
        row = await self.company_settings.get_current()
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "smtp_password" and value:
                value = encrypt(value)  # stored encrypted; see app/core/crypto.py
            if field == "email_signature":
                value = clean_signature(value)
            setattr(row, field, value)
        return await self.company_settings.save(row)
