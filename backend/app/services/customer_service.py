import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.customer import Customer
from app.models.user import User
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.customers = CustomerRepository(db)

    async def create_customer(self, data: CustomerCreate, created_by: User) -> Customer:
        customer = Customer(
            name=data.name,
            email=data.email,
            phone=data.phone,
            billing_address=data.billing_address,
            tax_number=data.tax_number,
            notes=data.notes,
            created_by=created_by.id,
        )
        return await self.customers.create(customer)

    async def list_customers(
        self,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> list[Customer]:
        return await self.customers.list_all(
            offset=offset, limit=limit, search=search, is_active=is_active
        )

    async def get_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
        return customer

    async def update_customer(self, customer_id: uuid.UUID, data: CustomerUpdate) -> Customer:
        customer = await self.get_customer(customer_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, field, value)
        return await self.customers.save(customer)

    async def deactivate_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.get_customer(customer_id)
        customer.is_active = False
        return await self.customers.save(customer)
