import uuid

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.crm import Contact
from app.models.customer import Customer
from app.schemas.crm import ContactCreate, ContactUpdate


def account_email_matches(address: str):
    """Match incoming mail to an account through any of its contact people."""
    normalized = address.strip().lower()
    return or_(
        func.lower(Customer.email) == normalized,
        exists().where(
            Contact.customer_id == Customer.id,
            Contact.company_id == Customer.company_id,
            func.lower(func.trim(Contact.email)) == normalized,
        ),
    )


class ContactService:
    """People at a customer. One contact per customer is primary: the
    person invoices and quotes are addressed to by default."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _customer(self, customer_id: uuid.UUID) -> Customer:
        customer = await self.db.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
        return customer

    async def get_contact(self, contact_id: uuid.UUID) -> Contact:
        contact = await self.db.get(Contact, contact_id)
        if contact is None:
            raise NotFoundError("Contact not found", "CONTACT_NOT_FOUND")
        return contact

    async def list_contacts(self, customer_id: uuid.UUID) -> list[Contact]:
        await self._customer(customer_id)
        result = await self.db.execute(
            select(Contact)
            .where(Contact.customer_id == customer_id)
            .order_by(Contact.is_primary.desc(), Contact.first_name, Contact.last_name)
        )
        return list(result.scalars().all())

    async def _clear_primary(self, customer_id: uuid.UUID, keep: uuid.UUID) -> None:
        await self.db.execute(
            update(Contact)
            .where(Contact.customer_id == customer_id, Contact.id != keep)
            .values(is_primary=False)
        )

    async def create_contact(self, customer_id: uuid.UUID, data: ContactCreate) -> Contact:
        await self._customer(customer_id)
        has_contacts = (
            await self.db.execute(select(Contact.id).where(Contact.customer_id == customer_id).limit(1))
        ).first()
        contact = Contact(
            customer_id=customer_id,
            **data.model_dump(exclude={"is_primary"}),
            # The first person added becomes primary without being asked.
            is_primary=data.is_primary or not has_contacts,
        )
        self.db.add(contact)
        await self.db.flush()
        if contact.is_primary:
            await self._clear_primary(customer_id, keep=contact.id)
        return contact

    async def update_contact(self, contact_id: uuid.UUID, data: ContactUpdate) -> Contact:
        contact = await self.get_contact(contact_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(contact, field, value)
        await self.db.flush()
        if data.is_primary:
            await self._clear_primary(contact.customer_id, keep=contact.id)
        return contact

    async def delete_contact(self, contact_id: uuid.UUID) -> None:
        contact = await self.get_contact(contact_id)
        await self.db.delete(contact)
        await self.db.flush()
