"""YGT's own sales pipeline, kept up to date from sign-ups and subscriptions.

Every company that signs up to YGT becomes a prospect in YGT's workspace
(the company of the first platform admin) with a deal at the stage its
subscription is at:

    trial running                  -> Negotiation (closes when the trial ends)
    paying (active or past due)    -> Won (the prospect becomes a customer)
    trial ended / lapsed / stopped -> Proposal (follow up to win them back)

The deal is worth their plan for a month (one seat while on trial). It
moves only when the subscription state changes (SubscriberLink.state), so a
stage set by hand stays until the subscriber's situation actually changes;
a deal deleted by hand is not recreated. Runs every few minutes
(billing_tasks); nothing is emailed.
"""
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.plans import PLANS, TRIAL_PLAN
from app.core.tenancy import set_system, set_tenant
from app.models.billing import SubscriberLink, Subscription
from app.models.company_settings import CompanySettings
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import DealStage, UserRole
from app.models.user import User
from app.schemas.crm import DealCreate, DealUpdate
from app.schemas.customer import ContactPerson, CustomerCreate
from app.services.billing_service import effective
from app.services.customer_service import CustomerService
from app.services.deal_service import DealService

logger = logging.getLogger(__name__)

STAGES = {
    "trialing": DealStage.NEGOTIATION,
    "active": DealStage.WON,
    "past_due": DealStage.WON,
    "cancelled": DealStage.PROPOSAL,
    "trial_ended": DealStage.PROPOSAL,
    "lapsed": DealStage.PROPOSAL,
}


@dataclass
class Change:
    company: str
    action: str  # "add" or "move"
    state: str
    stage: DealStage
    plan: str
    seats: int
    value: Decimal
    close: date | None


async def workspace(db) -> tuple[CompanySettings | None, User | None]:
    """YGT's own company and the admin whose deals these are: the first
    platform admin with a confirmed email."""
    if not settings.platform_admins:
        return None, None
    users = await db.scalars(select(User).where(func.lower(User.email).in_(settings.platform_admins), User.is_active.is_(True)).order_by(User.created_at))
    admin = next((u for u in users if u.is_platform_admin), None)
    return (await db.get(CompanySettings, admin.company_id), admin) if admin else (None, None)


async def sync(db, apply: bool = True, only: set | None = None) -> list[Change]:
    """Brings YGT's pipeline up to date; returns what changed (or, with
    apply=False, what would). `only`: just these company ids. The caller commits."""
    set_system(db)
    ygt, admin = await workspace(db)
    if ygt is None:
        return []
    links = {link.company_id: link for link in await db.scalars(select(SubscriberLink))}
    subs = {sub.company_id: sub for sub in await db.scalars(select(Subscription))}
    owners = {}
    for user in await db.scalars(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).order_by(User.created_at)):
        owners.setdefault(user.company_id, user)
    known = {name.strip().lower(): cid for cid, name in await db.execute(
        select(Customer.id, Customer.name).where(Customer.company_id == ygt.id).order_by(Customer.created_at))}

    work = []
    for company in await db.scalars(select(CompanySettings).where(CompanySettings.id != ygt.id).order_by(CompanySettings.created_at)):
        sub = subs.get(company.id)
        if sub is None or (only is not None and company.id not in only):
            continue
        state = effective(sub).state
        link = links.get(company.id)
        if link is not None and link.state == state:
            continue
        plan = PLANS.get(sub.plan) or PLANS[TRIAL_PLAN]
        seats = 1 if state in ("trialing", "trial_ended") else max(sub.seats or 1, 1)
        close = sub.trial_ends_at.date() if state == "trialing" and sub.trial_ends_at else None
        change = Change(company.company_name, "add" if link is None else "move", state, STAGES.get(state, DealStage.PROPOSAL),
                        plan.name, seats, Decimal(plan.price_cents("monthly", seats)) / 100, close)
        work.append((company, link, change))
    if not apply:
        return [change for _, _, change in work]

    set_tenant(db, ygt.id)  # every write below is in YGT's own workspace
    done = []
    for company, link, change in work:
        try:
            async with db.begin_nested():
                if link is None:
                    await _add(db, admin, company, owners.get(company.id), known.get(company.company_name.strip().lower()), change)
                else:
                    await _move(db, admin, link, change)
            done.append(change)
        except Exception:
            logger.exception("Couldn't update YGT's pipeline for %s", company.company_name)
    return done


async def _add(db, admin: User, company: CompanySettings, owner: User | None, customer_id, change: Change) -> None:
    deal = None
    if customer_id is None:
        customer = await CustomerService(db).create_customer(
            CustomerCreate(
                name=company.company_name,
                email=owner.email if owner else None,
                billing_address=company.address,
                notes=f"Signed up to YGT on {company.created_at:%Y-%m-%d}.",
                contact=ContactPerson(name=owner.full_name, email=owner.email) if owner and owner.full_name.strip() else None,
            ),
            created_by=admin,
            is_prospect=True,
        )
        customer_id = customer.id
    else:
        # Already in YGT's workspace (added by hand): carry on with their latest deal.
        deal = await db.scalar(select(Deal).where(Deal.customer_id == customer_id).order_by(Deal.created_at.desc()).limit(1))
    if deal is None:
        deal = await DealService(db).create_deal(
            DealCreate(title=f"{company.company_name} · YGT {change.plan}", customer_id=customer_id, owner_id=admin.id,
                       stage=change.stage, value=change.value, expected_close_date=change.close),
            created_by_id=admin.id,
        )
    else:
        await _update_deal(db, admin, deal.id, change)
    db.add(SubscriberLink(company_id=company.id, customer_id=customer_id, deal_id=deal.id, state=change.state))
    await db.flush()


async def _move(db, admin: User, link: SubscriberLink, change: Change) -> None:
    if link.deal_id is not None and await db.get(Deal, link.deal_id) is not None:
        await _update_deal(db, admin, link.deal_id, change)
    link.state = change.state
    await db.flush()


async def _update_deal(db, admin: User, deal_id, change: Change) -> None:
    try:
        async with db.begin_nested():
            await DealService(db).update_deal(
                deal_id, DealUpdate(stage=change.stage, value=change.value, expected_close_date=change.close), actor_id=admin.id)
    except AppError as exc:
        # E.g. an MCEM deal that needs evidence before it can move: leave the
        # stage to whoever runs it, but remember the state so we don't retry.
        logger.warning("Left the deal for %s at its stage: %s", change.company, exc)
