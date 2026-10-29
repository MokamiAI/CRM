import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Select, and_, exists, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import OPEN_DEAL_STAGES, InvoiceStatus
from app.models.invoice import Invoice
from app.models.marketing import Segment
from app.schemas.marketing import SegmentIn

_PURCHASE_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)
_OPEN_BALANCE_STATUSES = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE)


def _purchased_since(since: date):
    return exists().where(
        Invoice.customer_id == Customer.id,
        Invoice.status.in_(_PURCHASE_STATUSES),
        Invoice.issue_date >= since,
    )


def _condition(rule: dict):
    kind = rule["kind"]
    today = date.today()
    if kind == "custom_field":
        return Customer.custom_fields[rule["key"]].astext == str(rule["value"])
    if kind == "bought_within_days":
        return _purchased_since(today - timedelta(days=rule["days"]))
    if kind == "no_purchase_days":
        return not_(_purchased_since(today - timedelta(days=rule["days"])))
    if kind == "created_within_days":
        return Customer.created_at >= datetime.now(timezone.utc) - timedelta(days=rule["days"])
    if kind == "has_open_balance":
        cond = exists().where(Invoice.customer_id == Customer.id, Invoice.status.in_(_OPEN_BALANCE_STATUSES))
    elif kind == "has_open_deal":
        cond = exists().where(Deal.customer_id == Customer.id, Deal.stage.in_(OPEN_DEAL_STAGES))
    else:
        raise ValueError(f"unknown rule kind {kind!r}")
    return cond if rule.get("value", True) else not_(cond)


def audience_query(rules: list[dict]) -> Select:
    """Customers who can be emailed marketing and match every rule: active,
    with an email address, and not opted out. Prospects only once they've
    agreed to marketing (POPIA s69)."""
    return select(Customer).where(
        Customer.is_active.is_(True),
        or_(Customer.is_prospect.is_(False), Customer.marketing_consent_at.is_not(None)),
        Customer.recipient_email.is_not(None),
        Customer.recipient_email != "",
        Customer.marketing_opt_out.is_(False),
        and_(*(_condition(r) for r in rules)) if rules else True,
    )


class SegmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_segments(self) -> list[Segment]:
        return list((await self.db.scalars(select(Segment).order_by(Segment.name))).all())

    async def get_segment(self, segment_id: uuid.UUID) -> Segment:
        segment = await self.db.get(Segment, segment_id)
        if segment is None:
            raise NotFoundError("Audience not found", "SEGMENT_NOT_FOUND")
        return segment

    async def create_segment(self, data: SegmentIn) -> Segment:
        segment = Segment(name=data.name.strip(), rules=[r.model_dump() for r in data.rules])
        self.db.add(segment)
        await self.db.flush()
        return segment

    async def update_segment(self, segment_id: uuid.UUID, data: SegmentIn) -> Segment:
        segment = await self.get_segment(segment_id)
        segment.name = data.name.strip()
        segment.rules = [r.model_dump() for r in data.rules]
        await self.db.flush()
        return segment

    async def delete_segment(self, segment_id: uuid.UUID) -> None:
        await self.db.delete(await self.get_segment(segment_id))
        await self.db.flush()

    async def rules_for(self, segment_id: uuid.UUID | None) -> list[dict]:
        return [] if segment_id is None else (await self.get_segment(segment_id)).rules

    async def audience(self, rules: list[dict]) -> list[Customer]:
        return list((await self.db.scalars(audience_query(rules).order_by(Customer.name))).all())

    async def preview(self, rules: list[dict]) -> tuple[int, list[str]]:
        query = audience_query(rules).subquery()
        count = await self.db.scalar(select(func.count()).select_from(query))
        names = (await self.db.scalars(select(query.c.name).order_by(query.c.name).limit(5))).all()
        return count or 0, list(names)

