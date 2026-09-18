import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import QuoteStatus
from app.models.quote import Quote, QuoteItem
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.quote_repository import QuoteRepository
from app.schemas.quote import QuoteCreate, QuoteUpdate
from app.services.pricing import build_line_items

_ALLOWED_TRANSITIONS: dict[QuoteStatus, set[QuoteStatus]] = {
    QuoteStatus.DRAFT: {QuoteStatus.SENT},
    QuoteStatus.SENT: {QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED},
    QuoteStatus.ACCEPTED: {QuoteStatus.CONVERTED},
    QuoteStatus.REJECTED: set(),
    QuoteStatus.EXPIRED: set(),
    QuoteStatus.CONVERTED: set(),
}


class QuoteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.quotes = QuoteRepository(db)
        self.customers = CustomerRepository(db)
        self.company_settings = CompanySettingsRepository(db)

    async def create_quote(self, data: QuoteCreate, created_by_id: uuid.UUID) -> Quote:
        customer = await self.customers.get_by_id(data.customer_id)
        if customer is None or not customer.is_active:
            raise NotFoundError("Customer not found or inactive", "CUSTOMER_NOT_FOUND")

        items, subtotal, tax_total, total = build_line_items(QuoteItem, data.items)
        quote_number = await self.company_settings.reserve_next_quote_number()

        quote = Quote(
            quote_number=quote_number,
            customer_id=data.customer_id,
            issue_date=data.issue_date,
            expiry_date=data.expiry_date,
            notes=data.notes,
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            created_by=created_by_id,
            items=items,
        )
        return await self.quotes.create(quote)

    async def list_quotes(self, offset=0, limit=50, customer_id=None, status=None) -> list[Quote]:
        return await self.quotes.list_all(
            offset=offset, limit=limit, customer_id=customer_id, status=status
        )

    async def get_quote(self, quote_id: uuid.UUID) -> Quote:
        quote = await self.quotes.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found", "QUOTE_NOT_FOUND")
        return quote

    async def update_quote(self, quote_id: uuid.UUID, data: QuoteUpdate) -> Quote:
        quote = await self.get_quote(quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise ConflictError("Only draft quotes can be edited", "QUOTE_NOT_EDITABLE")

        if data.issue_date is not None:
            quote.issue_date = data.issue_date
        if data.expiry_date is not None:
            quote.expiry_date = data.expiry_date
        if data.notes is not None:
            quote.notes = data.notes
        if data.items is not None:
            items, subtotal, tax_total, total = build_line_items(QuoteItem, data.items)
            quote.items.clear()
            quote.items.extend(items)
            quote.subtotal = subtotal
            quote.tax_total = tax_total
            quote.total = total
        return await self.quotes.save(quote)

    async def transition_status(self, quote_id: uuid.UUID, new_status: QuoteStatus) -> Quote:
        quote = await self.get_quote(quote_id)
        allowed = _ALLOWED_TRANSITIONS.get(quote.status, set())
        if new_status not in allowed:
            raise ConflictError(
                f"Cannot move quote from {quote.status.value} to {new_status.value}",
                "QUOTE_INVALID_TRANSITION",
            )
        quote.status = new_status
        return await self.quotes.save(quote)

    async def delete_quote(self, quote_id: uuid.UUID) -> None:
        quote = await self.get_quote(quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise ConflictError("Only draft quotes can be deleted", "QUOTE_NOT_DELETABLE")
        await self.quotes.delete(quote)
