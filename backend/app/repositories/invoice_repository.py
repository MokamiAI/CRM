import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice


class InvoiceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        result = await self.db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 50,
        customer_id: uuid.UUID | None = None,
        status: InvoiceStatus | None = None,
    ) -> list[Invoice]:
        stmt = select(Invoice).options(selectinload(Invoice.items))
        if customer_id is not None:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        if status is not None:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def create(self, invoice: Invoice) -> Invoice:
        self.db.add(invoice)
        await self.db.flush()
        return invoice

    async def save(self, invoice: Invoice) -> Invoice:
        await self.db.flush()
        return invoice

    async def delete(self, invoice: Invoice) -> None:
        await self.db.delete(invoice)
        await self.db.flush()
