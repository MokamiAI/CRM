import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.crm import Contact
from app.models.customer import Customer
from app.models.user import User
from app.repositories.customer_repository import CustomerRepository
from app.schemas.crm import ContactCreate
from app.schemas.customer import ContactPerson, CustomerCreate, CustomerUpdate
from app.services.contact_service import ContactService
from app.services.custom_field_service import CustomFieldService


class CustomerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.customers = CustomerRepository(db)

    async def create_customer(self, data: CustomerCreate, created_by: User, *, is_prospect: bool = False) -> Customer:
        customer = Customer(
            name=data.name,
            is_prospect=is_prospect,
            email=data.email,
            phone=data.phone,
            billing_address=data.billing_address,
            delivery_address=data.delivery_address,
            tax_number=data.tax_number,
            notes=data.notes,
            custom_fields=await CustomFieldService(self.db).clean_values("customer", data.custom_fields),
            created_by=created_by.id,
        )
        customer = await self.customers.create(customer)
        if data.contact:
            await self._save_contact_person(customer, data.contact)
        return customer

    async def _save_contact_person(self, customer: Customer, person: ContactPerson) -> None:
        """The main contact: updated if the customer has one, else added."""
        first, _, last = person.name.strip().partition(" ")
        fields = {
            "first_name": first[:120],
            "last_name": last.strip()[:120] or None,
            "job_title": person.job_title or None,
            "email": person.email,
            "phone": person.phone or None,
        }
        primary = await self.db.scalar(select(Contact).where(Contact.customer_id == customer.id, Contact.is_primary.is_(True)))
        if primary:
            for key, value in fields.items():
                setattr(primary, key, value)
            await self.db.flush()
        else:
            await ContactService(self.db).create_contact(customer.id, ContactCreate(**fields, is_primary=True))

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
        changes = data.model_dump(exclude_unset=True)
        if changes.pop("contact", None) is not None:
            await self._save_contact_person(customer, data.contact)
        if changes.get("custom_fields") is not None:
            changes["custom_fields"] = await CustomFieldService(self.db).clean_values(
                "customer", changes["custom_fields"], customer.custom_fields
            )
        else:
            changes.pop("custom_fields", None)
        if "marketing_opt_out" in changes and changes["marketing_opt_out"] != customer.marketing_opt_out:
            customer.marketing_opt_out_at = datetime.now(timezone.utc) if changes["marketing_opt_out"] else None
        for field, value in changes.items():
            setattr(customer, field, value)
        return await self.customers.save(customer)

    async def deactivate_customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.get_customer(customer_id)
        customer.is_active = False
        return await self.customers.save(customer)
