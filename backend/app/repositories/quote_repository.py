import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import QuoteStatus
from app.models.quote import Quote


class QuoteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, quote_id: uuid.UUID) -> Quote | None:
        result = await self.db.execute(
            select(Quote).options(selectinload(Quote.items)).where(Quote.id == quote_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, quote_id: uuid.UUID) -> Quote | None:
        """The quote, row-locked until the transaction ends: two requests
        accepting or converting it at once take turns instead of both
        creating an invoice."""
        result = await self.db.execute(
            select(Quote).options(selectinload(Quote.items)).where(Quote.id == quote_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 50,
        customer_id: uuid.UUID | None = None,
        status: QuoteStatus | None = None,
    ) -> list[Quote]:
        stmt = select(Quote).options(selectinload(Quote.items))
        if customer_id is not None:
            stmt = stmt.where(Quote.customer_id == customer_id)
        if status is not None:
            stmt = stmt.where(Quote.status == status)
        stmt = stmt.order_by(Quote.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())

    async def create(self, quote: Quote) -> Quote:
        self.db.add(quote)
        await self.db.flush()
        return quote

    async def save(self, quote: Quote) -> Quote:
        await self.db.flush()
        return quote

    async def delete(self, quote: Quote) -> None:
        await self.db.delete(quote)
        await self.db.flush()
