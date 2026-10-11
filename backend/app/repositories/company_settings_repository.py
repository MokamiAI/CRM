import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.tenancy import current_company_id
from app.models.company_settings import CompanySettings


class CompanySettingsRepository:
    """Each company_settings row is one tenant ("company"). get_current()
    is the company the session is acting for (see app/core/tenancy.py)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for(self, company_id: uuid.UUID, *, for_update: bool = False) -> CompanySettings:
        query = select(CompanySettings).where(CompanySettings.id == company_id)
        if for_update:
            query = query.with_for_update()
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Company not found", "COMPANY_NOT_FOUND")
        return row

    async def get_current(self) -> CompanySettings:
        return await self.get_for(current_company_id(self.db))

    async def list_ids(self) -> list[uuid.UUID]:
        return list((await self.db.scalars(select(CompanySettings.id))).all())

    async def reserve_next_quote_number(self) -> str:
        # Row lock: two quotes created at once can't get the same number.
        row = await self.get_for(current_company_id(self.db), for_update=True)
        number = row.next_quote_number
        row.next_quote_number = number + 1
        await self.db.flush()
        return f"{row.quote_prefix}{number:04d}"

    async def reserve_next_po_number(self) -> str:
        row = await self.get_for(current_company_id(self.db), for_update=True)
        number = row.next_po_number
        row.next_po_number = number + 1
        await self.db.flush()
        return f"{row.po_prefix}{number:04d}"

    async def reserve_next_invoice_number(self) -> str:
        row = await self.get_for(current_company_id(self.db), for_update=True)
        number = row.next_invoice_number
        row.next_invoice_number = number + 1
        await self.db.flush()
        return f"{row.invoice_prefix}{number:04d}"

    async def save(self, row: CompanySettings) -> CompanySettings:
        await self.db.flush()
        return row
