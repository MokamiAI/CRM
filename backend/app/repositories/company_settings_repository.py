from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.company_settings import CompanySettings


class CompanySettingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_singleton(self) -> CompanySettings:
        # Assumes low-concurrency first use; a duplicate row from a lost
        # race on cold start is a one-time occurrence, not an ongoing risk.
        result = await self.db.execute(select(CompanySettings).limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            row = CompanySettings(
                company_name=settings.COMPANY_NAME,
                default_currency=settings.DEFAULT_CURRENCY,
                default_timezone=settings.DEFAULT_TIMEZONE,
            )
            self.db.add(row)
            await self.db.flush()
        return row

    async def reserve_next_quote_number(self) -> str:
        result = await self.db.execute(
            select(CompanySettings).limit(1).with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = await self.get_singleton()
        number = row.next_quote_number
        row.next_quote_number = number + 1
        await self.db.flush()
        return f"{row.quote_prefix}{number:04d}"

    async def reserve_next_invoice_number(self) -> str:
        result = await self.db.execute(
            select(CompanySettings).limit(1).with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = await self.get_singleton()
        number = row.next_invoice_number
        row.next_invoice_number = number + 1
        await self.db.flush()
        return f"{row.invoice_prefix}{number:04d}"

    async def save(self, row: CompanySettings) -> CompanySettings:
        await self.db.flush()
        return row
