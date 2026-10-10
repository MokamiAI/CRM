import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.crm import Activity, Contact, Deal
from app.models.customer import Customer
from app.models.enums import OPEN_DEAL_STAGES, DealStage
from app.schemas.crm import DealCreate, DealOut, DealUpdate, NextActivity
from app.services.custom_field_service import CustomFieldService

CLOSED_STAGES = {DealStage.WON, DealStage.LOST}


class DealService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_deal(self, deal_id: uuid.UUID) -> Deal:
        deal = await self.db.get(Deal, deal_id)
        if deal is None:
            raise NotFoundError("Deal not found", "DEAL_NOT_FOUND")
        return deal

    async def _check_links(self, customer_id: uuid.UUID, contact_id: uuid.UUID | None) -> None:
        customer = await self.db.get(Customer, customer_id)
        if customer is None or not customer.is_active:
            raise NotFoundError("Customer not found or inactive", "CUSTOMER_NOT_FOUND")
        if contact_id is not None:
            contact = await self.db.get(Contact, contact_id)
            if contact is None or contact.customer_id != customer_id:
                raise ConflictError("The contact must belong to the deal's customer", "CONTACT_CUSTOMER_MISMATCH")

    async def with_next_activity(self, deals: list[Deal]) -> list[DealOut]:
        """Attaches each deal's earliest open activity in one query, for
        the board's overdue / due today / nothing planned indicators."""
        if not deals:
            return []
        result = await self.db.execute(
            select(Activity)
            .where(Activity.deal_id.in_([d.id for d in deals]), Activity.done.is_(False))
            .order_by(Activity.due_date, Activity.due_time.nulls_last())
        )
        first: dict[uuid.UUID, Activity] = {}
        for activity in result.scalars():
            first.setdefault(activity.deal_id, activity)
        out = []
        for deal in deals:
            item = DealOut.model_validate(deal)
            if (activity := first.get(deal.id)) is not None:
                item.next_activity = NextActivity.model_validate(activity, from_attributes=True)
            out.append(item)
        return out

    async def list_deals(
        self,
        status: str = "open",
        owner_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> list[DealOut]:
        stmt = select(Deal)
        if status == "open":
            stmt = stmt.where(Deal.stage.in_(OPEN_DEAL_STAGES))
        elif status in ("won", "lost"):
            stmt = stmt.where(Deal.stage == DealStage(status))
        if owner_id is not None:
            stmt = stmt.where(Deal.owner_id == owner_id)
        if customer_id is not None:
            stmt = stmt.where(Deal.customer_id == customer_id)
        stmt = stmt.order_by(Deal.updated_at.desc()).limit(500)
        deals = list((await self.db.execute(stmt)).scalars().all())
        return await self.with_next_activity(deals)

    async def create_deal(self, data: DealCreate, created_by_id: uuid.UUID) -> Deal:
        await self._check_links(data.customer_id, data.contact_id)
        values = await CustomFieldService(self.db).clean_values("deal", data.custom_fields)
        deal = Deal(
            **data.model_dump(exclude={"custom_fields"}),
            custom_fields=values,
            created_by=created_by_id,
            closed_at=datetime.now(timezone.utc) if data.stage in CLOSED_STAGES else None,
        )
        # A new deal belongs to whoever created it unless assigned.
        if deal.owner_id is None:
            deal.owner_id = created_by_id
        self.db.add(deal)
        await self.db.flush()
        return deal

    async def update_deal(self, deal_id: uuid.UUID, data: DealUpdate) -> Deal:
        deal = await self.get_deal(deal_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("custom_fields") is not None:
            changes["custom_fields"] = await CustomFieldService(self.db).clean_values(
                "deal", changes["custom_fields"], deal.custom_fields
            )
        else:
            changes.pop("custom_fields", None)
        if "contact_id" in changes:
            await self._check_links(deal.customer_id, changes["contact_id"])
        new_stage = changes.get("stage")
        if new_stage is not None and new_stage != deal.stage:
            if new_stage in CLOSED_STAGES:
                deal.closed_at = datetime.now(timezone.utc)
            else:
                # Reopened: it's live again, so the old outcome no longer applies.
                deal.closed_at = None
                deal.lost_reason = None
        if new_stage is not None and new_stage != DealStage.LOST:
            changes.pop("lost_reason", None)
        for field, value in changes.items():
            setattr(deal, field, value)
        await self.db.flush()
        return deal

    async def delete_deal(self, deal_id: uuid.UUID) -> None:
        deal = await self.get_deal(deal_id)
        await self.db.delete(deal)
        await self.db.flush()
