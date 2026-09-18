import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        return await self.db.get(Payment, payment_id)

    async def list_for_invoice(self, invoice_id: uuid.UUID) -> list[Payment]:
        result = await self.db.execute(
            select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.paid_at)
        )
        return list(result.scalars().all())

    async def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        await self.db.flush()
        return payment

    async def delete(self, payment: Payment) -> None:
        await self.db.delete(payment)
        await self.db.flush()
