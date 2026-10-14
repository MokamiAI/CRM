"""Discovery (Scale): finds potential leads for a company, for a person to
add to the pipeline or dismiss. See app/models/discovery.py.

A run never adds anything to the pipeline by itself and never contacts the
leads: it only fills the Discovery list (and the weekly job emails the
company's admins about what's new)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.tenancy import current_company_id
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.discovery import DiscoveredLead, DiscoverySettings
from app.models.enums import DealStage, InvoiceStatus, QuoteStatus
from app.models.invoice import Invoice
from app.models.quote import Quote
from app.models.user import User
from app.schemas.crm import DealCreate
from app.schemas.customer import CustomerCreate
from app.services import discovery_osm

logger = logging.getLogger(__name__)

OPEN_STAGES = (DealStage.LEAD, DealStage.QUALIFIED, DealStage.PROPOSAL, DealStage.NEGOTIATION)
QUIET_AFTER_DAYS = 120  # a paying customer with nothing new for this long
LOST_MIN_DAYS, LOST_MAX_DAYS = 60, 365  # lost long enough ago to try again
QUOTE_MIN_DAYS, QUOTE_MAX_DAYS = 14, 120  # sent, never answered
MAX_NEARBY_PER_RUN = 25  # enough to review in one sitting
RUN_AGAIN_AFTER = timedelta(minutes=10)
_email = TypeAdapter(EmailStr)


class DiscoveryError(AppError):
    def __init__(self, message: str, error_code: str, status_code: int = 422):
        super().__init__(message, error_code, status_code)


def _norm(name: str) -> str:
    """Business names compared loosely: "ABC Solutions (Pty) Ltd" == "abc solutions"."""
    name = re.sub(r"\b(pty|ltd|cc|inc|npc|limited)\b", " ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


def _valid_email(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(_email.validate_python(value))
    except ValidationError:
        return None


def _money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.nearby_unavailable = False  # set by run() when the map service failed

    # ------------------------------------------------------------ settings

    async def settings(self) -> DiscoverySettings:
        row = await self.db.scalar(select(DiscoverySettings))
        if row is None:
            # Start from the industries the company already sells to.
            common = await self.db.scalars(
                select(Deal.industry)
                .where(Deal.industry.is_not(None), Deal.industry != "other")
                .group_by(Deal.industry)
                .order_by(func.count().desc())
                .limit(3)
            )
            row = DiscoverySettings(industries=list(common.all()))
            self.db.add(row)
            await self.db.flush()
        return row

    async def update_settings(self, *, enabled: bool, area: str | None, radius_km: int, industries: list[str]) -> DiscoverySettings:
        row = await self.settings()
        area = (area or "").strip() or None
        if area != row.area:
            row.latitude = row.longitude = None
            if area:
                try:
                    found = await discovery_osm.geocode(area)
                except discovery_osm.OsmUnavailable:
                    raise DiscoveryError("Couldn't reach the map service; try again in a minute", "DISCOVERY_UNAVAILABLE", 502)
                if found is None:
                    raise DiscoveryError("We couldn't find that place; try a suburb and town", "DISCOVERY_AREA_NOT_FOUND")
                row.latitude, row.longitude = found[0], found[1]
            row.area = area
        row.enabled, row.radius_km = enabled, radius_km
        row.industries = sorted(set(industries))
        await self.db.flush()
        return row

    # ------------------------------------------------------------ the list

    async def leads(self, status: str = "new") -> list[DiscoveredLead]:
        rows = await self.db.scalars(
            select(DiscoveredLead).where(DiscoveredLead.status == status).order_by(DiscoveredLead.created_at.desc(), DiscoveredLead.name).limit(200)
        )
        return list(rows.all())

    async def counts(self) -> dict[str, int]:
        rows = await self.db.execute(select(DiscoveredLead.status, func.count()).group_by(DiscoveredLead.status))
        return {status: n for status, n in rows.all()}

    async def _get(self, lead_id: uuid.UUID, lock: bool = False) -> DiscoveredLead:
        query = select(DiscoveredLead).where(DiscoveredLead.id == lead_id)
        lead = await self.db.scalar(query.with_for_update() if lock else query)
        if lead is None:
            raise NotFoundError("Lead not found", "LEAD_NOT_FOUND")
        return lead

    async def add_to_pipeline(self, lead_id: uuid.UUID, user: User, title: str | None = None) -> DiscoveredLead:
        """Makes the customer (for a new business) and a Lead-stage deal.
        The row lock means two clicks make one deal."""
        from app.services.billing_service import BillingService
        from app.services.customer_service import CustomerService
        from app.services.deal_service import DealService

        lead = await self._get(lead_id, lock=True)
        if lead.status != "new":
            raise DiscoveryError("This lead has already been handled", "LEAD_ALREADY_HANDLED", 409)
        customer_id = lead.customer_id
        if customer_id is None:
            await BillingService(self.db).check_room("customers")
            customer = await CustomerService(self.db).create_customer(
                CustomerCreate(
                    name=lead.name,
                    email=_valid_email(lead.email),
                    phone=lead.phone,
                    billing_address=lead.address,
                    notes="\n".join(p for p in ("Found by Discovery (© OpenStreetMap contributors).", lead.website) if p),
                ),
                created_by=user,
            )
            customer_id = customer.id
        value = Decimal(lead.details.get("value") or 0)
        deal = await DealService(self.db).create_deal(
            DealCreate(title=(title or lead.name)[:255], customer_id=customer_id, stage=DealStage.LEAD, value=value, industry=lead.industry),
            created_by_id=user.id,
        )
        if lead.source == "stale_quote":
            # Tie the unanswered quote to its new deal, if it had none.
            quote = await self.db.scalar(select(Quote).where(Quote.id == uuid.UUID(lead.details["quote_id"])))
            if quote is not None and quote.deal_id is None:
                quote.deal_id = deal.id
        lead.status, lead.customer_id, lead.deal_id = "added", customer_id, deal.id
        lead.decided_at, lead.decided_by = datetime.now(timezone.utc), user.id
        await self.db.flush()
        return lead

    async def dismiss(self, lead_id: uuid.UUID, user: User) -> DiscoveredLead:
        lead = await self._get(lead_id, lock=True)
        if lead.status == "new":
            lead.status, lead.decided_at, lead.decided_by = "dismissed", datetime.now(timezone.utc), user.id
            await self.db.flush()
        return lead

    # ------------------------------------------------------------ finding

    async def run(self, today: date, *, manual: bool = False) -> list[DiscoveredLead]:
        """Looks in both places and saves what's new. Returns the new leads.

        By hand (manual), only the company's own records are checked here:
        the map lookup can take a minute or more when OpenStreetMap is busy,
        so the route runs look_nearby() after answering, and the page shows
        "looking" until it's done."""
        conf = await self.settings()
        now = datetime.now(timezone.utc)
        if manual and conf.last_run_at and now - conf.last_run_at < RUN_AGAIN_AFTER:
            raise DiscoveryError("Discovery ran a few minutes ago; try again shortly", "DISCOVERY_TOO_SOON", 429)
        conf.last_run_at = now
        found = await self._save(await self._own_records(today))
        if self.can_look_nearby(conf):
            if manual:
                conf.nearby_status, conf.nearby_checked_at = "looking", now
            else:
                found += await self.look_nearby()
        await self.db.flush()
        return found

    @staticmethod
    def can_look_nearby(conf: DiscoverySettings) -> bool:
        return conf.latitude is not None and bool(conf.industries)

    async def look_nearby(self) -> list[DiscoveredLead]:
        """Businesses near the company on OpenStreetMap. A busy map service
        leaves nearby_status "failed"; the next run tries again."""
        conf = await self.settings()
        conf.nearby_checked_at = datetime.now(timezone.utc)
        try:
            found = await self._save(await self._nearby(conf))
        except discovery_osm.OsmUnavailable:
            conf.nearby_status = "failed"
            self.nearby_unavailable = True
            await self.db.flush()
            return []
        conf.nearby_status = "done"
        await self.db.flush()
        return found

    async def _save(self, candidates: list[dict]) -> list[DiscoveredLead]:
        if not candidates:
            return []
        company_id = current_company_id(self.db)
        rows = [{"id": uuid.uuid4(), "company_id": company_id, "status": "new", **c} for c in candidates]
        stmt = insert(DiscoveredLead).values(rows).on_conflict_do_nothing(constraint="uq_discovered_leads_ref").returning(DiscoveredLead.id)
        new_ids = list((await self.db.execute(stmt)).scalars().all())
        await self.db.flush()
        if not new_ids:
            return []
        return list((await self.db.scalars(select(DiscoveredLead).where(DiscoveredLead.id.in_(new_ids)).order_by(DiscoveredLead.name))).all())

    async def _nearby(self, conf: DiscoverySettings) -> list[dict]:
        places = await discovery_osm.nearby(conf.latitude, conf.longitude, conf.radius_km, conf.industries)
        known = {_norm(n) for n in (await self.db.scalars(select(Customer.name))).all()}
        seen = set((await self.db.scalars(select(DiscoveredLead.external_ref).where(DiscoveredLead.source == "osm"))).all())
        out = []
        for p in places:
            if p.ref in seen or _norm(p.name) in known:
                continue
            known.add(_norm(p.name))  # one branch of a chain is enough
            out.append(
                {
                    "source": "osm",
                    "external_ref": p.ref,
                    "name": p.name,
                    "industry": p.industry,
                    "kind": p.kind,
                    "address": p.address,
                    "phone": p.phone,
                    "email": _valid_email(p.email),
                    "website": p.website,
                    "details": {},
                }
            )
            if len(out) >= MAX_NEARBY_PER_RUN:
                break
        return out

    async def _own_records(self, today: date) -> list[dict]:
        """Customers worth a call: one reason each, the strongest first."""
        open_deal = select(Deal.customer_id).where(Deal.stage.in_(OPEN_STAGES))
        pending = select(DiscoveredLead.customer_id).where(DiscoveredLead.status == "new", DiscoveredLead.customer_id.is_not(None))
        busy = set((await self.db.scalars(open_deal)).all()) | set((await self.db.scalars(pending)).all())
        out: list[dict] = []

        def take(customer: Customer, source: str, ref: str, details: dict, last: date | None) -> None:
            busy.add(customer.id)
            out.append(
                {
                    "source": source,
                    "external_ref": ref,
                    "name": customer.name,
                    "customer_id": customer.id,
                    "email": customer.email,
                    "phone": customer.phone,
                    "address": customer.billing_address,
                    "details": details,
                    "last_contact": last,
                }
            )

        # 1. Sent quotes nobody answered.
        quotes = await self.db.execute(
            select(Quote, Customer)
            .join(Customer, Customer.id == Quote.customer_id)
            .where(
                Customer.is_active.is_(True),
                Quote.status.in_((QuoteStatus.SENT, QuoteStatus.EXPIRED)),
                Quote.issue_date.between(today - timedelta(days=QUOTE_MAX_DAYS), today - timedelta(days=QUOTE_MIN_DAYS)),
            )
            .order_by(Quote.total.desc())
        )
        for quote, customer in quotes.all():
            if customer.id not in busy:
                details = {"quote_id": str(quote.id), "number": quote.quote_number, "value": _money(quote.total)}
                take(customer, "stale_quote", f"quote:{quote.id}", details, quote.issue_date)

        # 2. Deals lost a while ago.
        lost = await self.db.execute(
            select(Deal, Customer)
            .join(Customer, Customer.id == Deal.customer_id)
            .where(
                Customer.is_active.is_(True),
                Deal.stage == DealStage.LOST,
                func.date(Deal.closed_at).between(today - timedelta(days=LOST_MAX_DAYS), today - timedelta(days=LOST_MIN_DAYS)),
            )
            .order_by(Deal.value.desc())
        )
        for deal, customer in lost.all():
            if customer.id not in busy:
                details = {"deal_id": str(deal.id), "title": deal.title, "value": _money(deal.value), "reason": deal.lost_reason}
                take(customer, "lost_deal", f"lost:{deal.id}", details, deal.closed_at.date() if deal.closed_at else None)

        # 3. Paying customers who have gone quiet.
        last_invoice = select(Invoice.customer_id, func.max(Invoice.issue_date).label("last"), func.avg(Invoice.total).label("avg")).where(
            Invoice.status == InvoiceStatus.PAID
        ).group_by(Invoice.customer_id).subquery()
        last_quote = select(Quote.customer_id, func.max(Quote.issue_date).label("last")).group_by(Quote.customer_id).subquery()
        last_deal = select(Deal.customer_id, func.max(func.date(Deal.created_at)).label("last")).group_by(Deal.customer_id).subquery()
        any_invoice = select(Invoice.customer_id, func.max(Invoice.issue_date).label("last")).group_by(Invoice.customer_id).subquery()
        latest = func.greatest(any_invoice.c.last, func.coalesce(last_quote.c.last, any_invoice.c.last), func.coalesce(last_deal.c.last, any_invoice.c.last))
        quiet = await self.db.execute(
            select(Customer, latest.label("latest"), last_invoice.c.avg)
            .join(last_invoice, last_invoice.c.customer_id == Customer.id)
            .join(any_invoice, any_invoice.c.customer_id == Customer.id)
            .outerjoin(last_quote, last_quote.c.customer_id == Customer.id)
            .outerjoin(last_deal, last_deal.c.customer_id == Customer.id)
            .where(Customer.is_active.is_(True), latest <= today - timedelta(days=QUIET_AFTER_DAYS))
            .order_by(last_invoice.c.avg.desc())
        )
        for customer, latest_day, avg in quiet.all():
            if customer.id not in busy:
                take(customer, "quiet_customer", f"quiet:{customer.id}:{latest_day.isoformat()}", {"value": _money(avg)}, latest_day)
        return out
