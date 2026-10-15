"""Settings > Billing: the company's YGT plan, paid through Paystack."""
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import PLANS, Plan
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.billing import (
    BillingOut,
    CheckoutIn,
    CheckoutOut,
    ConfirmIn,
    ConfirmOut,
    LinkOut,
    Limits,
    PaymentOut,
    PlanOut,
    SubscriptionInvoiceOut,
    Usage,
)
from app.core.exceptions import NotFoundError
from app.models.billing import SubscriptionInvoice
from app.services import paystack, subscription_invoices
from app.services.billing_service import BillingService, effective

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/billing", tags=["billing"])
_admin = Depends(require_role(UserRole.ADMIN))


def plan_out(plan: Plan) -> PlanOut:
    return PlanOut(
        key=plan.key,
        name=plan.name,
        monthly_cents=plan.monthly_cents,
        annual_cents=plan.price_cents("annually"),
        per_user=plan.per_user,
        min_users=plan.min_users,
        max_users=plan.max_users,
        max_customers=plan.max_customers,
        invoices_per_month=plan.invoices_per_month,
        features=sorted(plan.features),
    )


async def billing_out(service: BillingService) -> BillingOut:
    sub = await service.subscription()
    current = effective(sub)
    return BillingOut(
        plan=current.plan.key,
        state=current.state,
        subscribed_plan=sub.plan if sub.status in ("active", "past_due", "cancelled") else None,
        interval=sub.interval,
        seats=sub.seats,
        trial_ends_at=sub.trial_ends_at,
        current_period_end=sub.current_period_end,
        features=sorted(current.plan.features),
        usage=Usage(**await service.usage()),
        limits=Limits(users=current.users, customers=current.plan.max_customers, invoices_this_month=current.plan.invoices_per_month),
        has_card=bool(sub.paystack_subscription_code),
        payments_enabled=paystack.configured(),
    )


@router.get("/plans", response_model=list[PlanOut])
async def plans(_: User = Depends(get_current_user)):
    return [plan_out(p) for p in PLANS.values()]


@router.get("", response_model=BillingOut)
async def get_billing(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await billing_out(BillingService(db))


@router.post("/checkout", response_model=CheckoutOut, dependencies=[_admin])
async def checkout(data: CheckoutIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    url = await BillingService(db).checkout(user, data.plan, data.interval, data.users)
    return CheckoutOut(authorization_url=url)


@router.post("/confirm", response_model=ConfirmOut, dependencies=[_admin])
async def confirm(data: ConfirmIn, db: AsyncSession = Depends(get_db)):
    service = BillingService(db)
    confirmed = await service.confirm(data.reference)
    return ConfirmOut(confirmed=confirmed, billing=await billing_out(service))


@router.post("/cancel", response_model=BillingOut, dependencies=[_admin])
async def cancel(db: AsyncSession = Depends(get_db)):
    service = BillingService(db)
    await service.cancel()
    return await billing_out(service)


@router.post("/card", response_model=LinkOut, dependencies=[_admin])
async def manage_card(db: AsyncSession = Depends(get_db)):
    return LinkOut(url=await BillingService(db).manage_link())


@router.get("/payments", response_model=list[PaymentOut], dependencies=[_admin])
async def payments(db: AsyncSession = Depends(get_db)):
    return await BillingService(db).payments()


@router.get("/invoices", response_model=list[SubscriptionInvoiceOut], dependencies=[_admin])
async def invoices(db: AsyncSession = Depends(get_db)):
    """YGT's invoices to this company, newest first (one per payment)."""
    rows = await db.scalars(select(SubscriptionInvoice).order_by(SubscriptionInvoice.issued_at.desc()).limit(60))
    return list(rows.all())


@router.get("/invoices/{invoice_id}/document", response_class=HTMLResponse, dependencies=[_admin])
async def invoice_document(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    invoice = await db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.id == invoice_id))
    if invoice is None:
        raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
    return HTMLResponse(subscription_invoices.render_html(invoice))
