"""Subscriptions: what each company's plan lets it do, checkout through
Paystack, and keeping the plan in step with Paystack's webhooks.

What a company can use right now is worked out on read (effective()), so
an ended trial or a lapsed payment needs no scheduled job: from that
moment the company is read-only (LOCKED), and keeps all its data."""
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.plans import GRACE_DAYS, LOCKED, PLANS, TRIAL_PLAN, TRIAL_USERS, Plan
from app.core.tenancy import current_company_id, set_system, set_tenant
from app.models.billing import BillingPayment, PaystackPlan, Subscription
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.user import User
from app.services import paystack, platform_email, subscription_invoices

logger = logging.getLogger(__name__)


class PlanLimitError(AppError):
    """The company's plan doesn't allow this. 402 so the app can offer an upgrade."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message, error_code, status.HTTP_402_PAYMENT_REQUIRED)


@dataclass
class Effective:
    plan: Plan
    users: int | None  # how many active people may sign in; None: no limit
    state: str  # trialing | active | past_due | cancelled | trial_ended | lapsed

    @property
    def locked(self) -> bool:
        return self.plan is LOCKED


def _now() -> datetime:
    return datetime.now(timezone.utc)


def effective(sub: Subscription, now: datetime | None = None) -> Effective:
    now = now or _now()
    if sub.status == "trialing":
        if sub.trial_ends_at and sub.trial_ends_at > now:
            plan = PLANS.get(sub.plan, PLANS[TRIAL_PLAN])
            return Effective(plan, trial_users(plan), "trialing")
        return Effective(LOCKED, None, "trial_ended")
    if sub.status in ("active", "past_due", "cancelled") and sub.plan in PLANS:
        plan = PLANS[sub.plan]
        # Cancelled: paid up to the end of the period. Active/past due: a few
        # extra days while Paystack retries the card.
        grace = timedelta(0) if sub.status == "cancelled" else timedelta(days=GRACE_DAYS)
        if sub.current_period_end and sub.current_period_end + grace > now:
            return Effective(plan, plan.user_limit(sub.seats), sub.status)
        return Effective(LOCKED, None, "lapsed")
    return Effective(LOCKED, None, "trial_ended")


def trial_users(plan: Plan) -> int:
    """People allowed during a trial: the plan's own limit, or TRIAL_USERS
    for plans priced per person."""
    return TRIAL_USERS if plan.per_user else plan.max_users


def new_trial(company_id: uuid.UUID, plan_key: str = TRIAL_PLAN) -> Subscription:
    """A free trial of the plan chosen at sign-up, with exactly its features."""
    plan = PLANS.get(plan_key, PLANS[TRIAL_PLAN])
    return Subscription(
        company_id=company_id,
        plan=plan.key,
        status="trialing",
        interval="monthly",
        seats=trial_users(plan),
        trial_ends_at=_now() + timedelta(days=settings.TRIAL_DAYS),
    )


def _add_interval(start: datetime, interval: str) -> datetime:
    if interval == "annually":
        try:
            return start.replace(year=start.year + 1)
        except ValueError:  # 29 February
            return start.replace(year=start.year + 1, day=28)
    month = start.month % 12 + 1
    year = start.year + (start.month == 12)
    for day in (start.day, 30, 29, 28):
        try:
            return start.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError("unreachable")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class BillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------ reading

    async def subscription(self) -> Subscription:
        sub = await self.db.scalar(select(Subscription))
        if sub is None:
            # Companies created before billing existed, or by hand.
            sub = new_trial(current_company_id(self.db))
            self.db.add(sub)
            await self.db.flush()
        return sub

    async def current(self) -> Effective:
        return effective(await self.subscription())

    async def usage(self) -> dict[str, int]:
        month_start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = lambda q: self.db.scalar(select(func.count()).select_from(q.subquery()))  # noqa: E731
        return {
            "users": await count(select(User.id).where(User.is_active.is_(True))),
            "customers": await count(select(Customer.id).where(Customer.is_active.is_(True))),
            "invoices_this_month": await count(select(Invoice.id).where(Invoice.created_at >= month_start)),
        }

    async def payments(self) -> list[BillingPayment]:
        return list(await self.db.scalars(select(BillingPayment).order_by(BillingPayment.paid_at.desc()).limit(24)))

    # ------------------------------------------------------------ limits

    async def ensure_active(self) -> None:
        """Before any change: a trial or paid plan must be running."""
        current = await self.current()
        if current.locked:
            raise PlanLimitError("Your trial or plan has ended; choose a plan to keep working", "PLAN_EXPIRED")

    async def require_feature(self, feature: str) -> None:
        current = await self.current()
        if feature not in current.plan.features:
            raise PlanLimitError(f"Your plan doesn't include this ({feature})", f"PLAN_FEATURE_{feature.upper()}")

    async def check_room(self, what: str) -> None:
        """Before adding a person, customer or invoice: is there room on the plan?"""
        current = await self.current()
        limit = {
            "users": current.users,
            "customers": current.plan.max_customers,
            "invoices_this_month": current.plan.invoices_per_month,
        }[what]
        if limit is not None and (await self.usage())[what] >= limit:
            raise PlanLimitError(f"Your plan allows {limit} {what.replace('_', ' ')}", f"PLAN_LIMIT_{what.upper()}")

    # ------------------------------------------------------------ checkout

    async def _plan_code(self, plan: Plan, interval: str, users: int, fresh: bool = False) -> tuple[str, int]:
        users = users if plan.per_user else 1
        # Plans belong to one Paystack account and mode (test and live keys
        # see different plans), so remember them per secret key.
        account = hashlib.sha256(settings.PAYSTACK_SECRET_KEY.encode()).hexdigest()[:8]
        key = f"{account}:{plan.key}:{interval}:{users}"
        amount = plan.price_cents(interval, users)
        saved = await self.db.scalar(select(PaystackPlan).where(PaystackPlan.key == key))
        if saved and saved.amount_cents == amount and not fresh:
            return saved.plan_code, amount
        label = f"YGT {plan.name} ({interval}" + (f", {users} seats)" if plan.per_user else ")")
        code = await paystack.create_plan(label, amount, interval)
        if saved:
            saved.plan_code, saved.amount_cents = code, amount
        else:
            self.db.add(PaystackPlan(key=key, plan_code=code, amount_cents=amount))
        await self.db.flush()
        return code, amount

    async def checkout(self, user: User, plan_key: str, interval: str, users: int) -> str:
        plan = PLANS[plan_key]
        if not plan.paid:
            raise AppError("Choose a paid plan", "BILLING_PLAN_INVALID")
        users = max(users, plan.min_users) if plan.per_user else 1
        if plan.per_user and users < (await self.usage())["users"]:
            raise AppError("Choose at least as many users as are active now", "BILLING_TOO_FEW_USERS")
        sub = await self.subscription()

        async def start(fresh: bool) -> str:
            code, amount = await self._plan_code(plan, interval, users, fresh=fresh)
            return await paystack.initialize(
                email=sub.billing_email or user.email,
                amount_cents=amount,
                plan_code=code,
                reference=f"ygt_{uuid.uuid4().hex}",
                callback_url=f"{settings.FRONTEND_URL.rstrip('/')}/settings?tab=billing",
                metadata={"company_id": str(sub.company_id), "plan": plan.key, "interval": interval, "seats": users},
            )

        try:
            return await start(fresh=False)
        except paystack.PaystackError as exc:
            # The remembered plan is gone on Paystack's side (deleted in the
            # dashboard, or a different account): make it again, once.
            if "plan not found" not in exc.message.lower():
                raise
            return await start(fresh=True)

    async def confirm(self, reference: str) -> bool:
        """After Paystack sends the person back: check the payment and switch
        the plan on straight away, without waiting for the webhook."""
        data = await paystack.verify(reference)
        if data.get("status") != "success":
            return False
        if (data.get("metadata") or {}).get("company_id") != str(current_company_id(self.db)):
            raise AppError("This payment belongs to another account", "BILLING_REFERENCE_MISMATCH", status.HTTP_403_FORBIDDEN)
        await self._apply_charge(await self.subscription(), data)
        return True

    async def _charge_matches_plan(self, data: dict, plan_code: str | None) -> bool:
        """The charge is in rand, for a plan YGT created, and for at least that
        plan's amount. Checked against the amount the plan was created with,
        so renewals at an older price still go through after a price change."""
        if (data.get("currency") or "").upper() != "ZAR" or not plan_code:
            return False
        expected = await self.db.scalar(select(PaystackPlan.amount_cents).where(PaystackPlan.plan_code == plan_code))
        return expected is not None and int(data.get("amount") or 0) >= expected

    async def _apply_charge(self, sub: Subscription, data: dict) -> None:
        reference = data.get("reference")
        # The redirect back and the webhook can arrive together: take turns.
        await self.db.execute(select(Subscription.id).where(Subscription.id == sub.id).with_for_update())
        if reference and await self.db.scalar(select(BillingPayment.id).where(BillingPayment.reference == reference)):
            return  # already recorded (confirm and webhook both arrive)
        meta = data.get("metadata") or {}
        plan_code = data.get("plan") if isinstance(data.get("plan"), str) else (data.get("plan") or {}).get("plan_code")
        if not await self._charge_matches_plan(data, plan_code):
            # Signed by Paystack, but not a full rand payment for one of our
            # own plans: record nothing and leave the plan as it is.
            logger.warning("Paystack charge %s not applied: amount, currency or plan does not match", reference)
            return
        if meta.get("plan") in PLANS:
            # A new checkout: take the plan chosen there.
            sub.plan, sub.interval, sub.seats = meta["plan"], meta.get("interval", "monthly"), int(meta.get("seats") or 1)
        paid_at = _parse_time(data.get("paid_at") or data.get("paidAt")) or _now()
        previous_code, previous_token = sub.paystack_subscription_code, sub.paystack_email_token
        replacing = bool(meta.get("plan")) and previous_code and plan_code and plan_code != sub.paystack_plan_code
        sub.status = "active"
        sub.trial_ends_at = None
        sub.current_period_end = _add_interval(paid_at, sub.interval)
        customer = data.get("customer") or {}
        sub.paystack_customer_code = customer.get("customer_code") or sub.paystack_customer_code
        sub.billing_email = customer.get("email") or sub.billing_email
        if plan_code:
            sub.paystack_plan_code = plan_code
        payment = BillingPayment(
            company_id=sub.company_id,
            reference=reference or f"ygt_{uuid.uuid4().hex}",
            amount_cents=int(data.get("amount") or 0),
            currency=data.get("currency") or "ZAR",
            plan=sub.plan,
            interval=sub.interval,
            seats=sub.seats,
            paid_at=paid_at,
        )
        self.db.add(payment)
        await self.db.flush()
        await self._link_subscription(sub, customer.get("id"))
        # Changing plan: stop the old Paystack subscription so the card isn't charged twice.
        if replacing and previous_token and previous_code != sub.paystack_subscription_code:
            try:
                await paystack.disable(previous_code, previous_token)
            except paystack.PaystackError:
                pass
        # YGT's invoice for this payment, emailed to the company's admins
        # and billing contact once everything above is saved.
        invoice = await subscription_invoices.issue_for_payment(self.db, payment, sub.current_period_end)
        if invoice is not None:
            to = await subscription_invoices.recipients(self.db, sub.company_id, sub.billing_email)
            await platform_email.queue(self.db, *(subscription_invoices.email_for(invoice, address) for address in to))

    async def _link_subscription(self, sub: Subscription, customer_id) -> None:
        """Find the Paystack subscription the charge created, so it can be
        cancelled or have its card changed later."""
        if not customer_id or not sub.paystack_plan_code:
            return
        try:
            found = await paystack.subscriptions_for(customer_id)
        except paystack.PaystackError:
            return  # the subscription.create webhook fills it in instead
        for item in found:
            plan = item.get("plan") or {}
            if plan.get("plan_code") == sub.paystack_plan_code and item.get("status") in ("active", "non-renewing"):
                sub.paystack_subscription_code = item.get("subscription_code")
                sub.paystack_email_token = item.get("email_token")
                sub.current_period_end = _parse_time(item.get("next_payment_date")) or sub.current_period_end
                break

    async def cancel(self) -> Subscription:
        sub = await self.subscription()
        if sub.status not in ("active", "past_due"):
            raise AppError("There's no paid plan to cancel", "BILLING_NOTHING_TO_CANCEL")
        if sub.paystack_subscription_code and sub.paystack_email_token:
            await paystack.disable(sub.paystack_subscription_code, sub.paystack_email_token)
        sub.status = "cancelled"
        await self.db.flush()
        return sub

    async def manage_link(self) -> str:
        sub = await self.subscription()
        if not sub.paystack_subscription_code:
            raise AppError("There's no card on file yet", "BILLING_NO_SUBSCRIPTION")
        return await paystack.manage_link(sub.paystack_subscription_code)

    # ------------------------------------------------------------ webhook

    async def _find(self, data: dict) -> Subscription | None:
        """The company a Paystack event is about: from our checkout metadata,
        else the subscription or customer code we stored."""
        set_system(self.db)
        meta = data.get("metadata") or {}
        sub = None
        if meta.get("company_id"):
            try:
                sub = await self.db.scalar(select(Subscription).where(Subscription.company_id == uuid.UUID(meta["company_id"])))
            except ValueError:
                sub = None
        if sub is None and data.get("subscription_code"):
            sub = await self.db.scalar(select(Subscription).where(Subscription.paystack_subscription_code == data["subscription_code"]))
        customer_code = (data.get("customer") or {}).get("customer_code")
        if sub is None and customer_code:
            sub = await self.db.scalar(select(Subscription).where(Subscription.paystack_customer_code == customer_code))
        if sub is not None:
            set_tenant(self.db, sub.company_id)
        return sub

    async def handle_event(self, event: str, data: dict) -> None:
        sub = await self._find(data)
        if sub is None:
            return
        if event == "charge.success" and data.get("plan"):
            await self._apply_charge(sub, data)
        elif event == "subscription.create":
            plan_code = (data.get("plan") or {}).get("plan_code")
            if plan_code and plan_code == sub.paystack_plan_code:
                sub.paystack_subscription_code = data.get("subscription_code")
                sub.paystack_email_token = data.get("email_token")
                sub.current_period_end = _parse_time(data.get("next_payment_date")) or sub.current_period_end
        elif event in ("subscription.disable", "subscription.not_renew"):
            if data.get("subscription_code") == sub.paystack_subscription_code:
                sub.status = "cancelled"
        elif event == "invoice.payment_failed":
            subscription = data.get("subscription") or {}
            if subscription.get("subscription_code") in (None, sub.paystack_subscription_code) and sub.status == "active":
                sub.status = "past_due"
        await self.db.flush()
