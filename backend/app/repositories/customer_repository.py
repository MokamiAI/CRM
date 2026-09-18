import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer


class CustomerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, customer_id: uuid.UUID) -> Customer | None:
        return await self.db.get(Customer, customer_id)

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Customer]:
        stmt = select(Customer)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(or_(Customer.name.ilike(pattern), Customer.email.ilike(pattern)))
        if is_active is not None:
            stmt = stmt.where(Customer.is_active == is_active)
        stmt = stmt.order_by(Customer.name).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, customer: Customer) -> Customer:
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def save(self, customer: Customer) -> Customer:
        await self.db.flush()
        return customer
