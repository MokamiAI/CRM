"""The admin site's view across every company: tenants and their totals,
subscriptions and refunds, errors and activity. Runs in a SYSTEM session
(see require_platform_admin), so nothing here is filtered by company."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.plans import PLANS
from app.models.billing import BillingPayment, Subscription, SubscriptionInvoice
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.models.enums import InvoiceStatus, UserRole
from app.models.invoice import Invoice
from app.models.platform import AuditEvent, BillingRefund, ContactRequest, ErrorLog, SessionBooking, SupportTicket
from app.models.quote import Quote
from app.models.user import User
from app.services import paystack
from app.services.billing_service import effective

logger = logging.getLogger(__name__)

_BILLED = (InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.OVERDUE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def monthly_cents(sub: Subscription) -> int:
    """What a paying subscription is worth per month (MRR)."""
    if sub.status not in ("active", "past_due") or sub.plan not in PLANS:
        return 0
    price = PLANS[sub.plan].price_cents(sub.interval, sub.seats)
    return round(price / 12) if sub.interval == "annually" else price


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count_by_company(self, model, *where) -> dict[uuid.UUID, int]:
        rows = await self.db.execute(select(model.company_id, func.count()).where(*where).group_by(model.company_id))
        return dict(rows.all())

    async def overview(self) -> dict:
        subs = list(await self.db.scalars(select(Subscription)))
        states = {"trialing": 0, "active": 0, "past_due": 0, "cancelled": 0, "locked": 0}
        for sub in subs:
            current = effective(sub)
            states["locked" if current.locked else current.state] = states.get("locked" if current.locked else current.state, 0) + 1
        since = _now() - timedelta(days=30)
        revenue = await self.db.scalar(select(func.coalesce(func.sum(BillingPayment.amount_cents), 0)).where(BillingPayment.paid_at >= since))
        refunded = await self.db.scalar(
            select(func.coalesce(func.sum(BillingRefund.amount_cents), 0)).where(BillingRefund.created_at >= since, BillingRefund.status != "failed")
        )
        count = lambda q: self.db.scalar(select(func.count()).select_from(q.subquery()))  # noqa: E731
        return {
            "tenants": await self.db.scalar(select(func.count()).select_from(CompanySettings)),
            "suspended": await self.db.scalar(select(func.count()).select_from(CompanySettings).where(CompanySettings.suspended_at.is_not(None))),
            "states": states,
            "mrr_cents": sum(monthly_cents(s) for s in subs),
            "revenue_30d_cents": int(revenue) - int(refunded),
            "users": await self.db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))),
            "open_tickets": await count(select(SupportTicket.id).where(SupportTicket.status.in_(("open", "in_progress")))),
            "priority_tickets": await count(select(SupportTicket.id).where(SupportTicket.status.in_(("open", "in_progress")), SupportTicket.priority_plan.is_(True))),
            "new_contacts": await count(select(ContactRequest.id).where(ContactRequest.status == "new")),
            "errors_24h": await count(select(ErrorLog.id).where(ErrorLog.created_at >= _now() - timedelta(hours=24))),
            "upcoming_bookings": await count(select(SessionBooking.id).where(SessionBooking.status == "booked", SessionBooking.starts_at >= _now())),
            "signups_30d": await self.db.scalar(select(func.count()).select_from(CompanySettings).where(CompanySettings.created_at >= since)),
        }

    async def tenants(self, search: str | None = None) -> list[dict]:
        query = select(CompanySettings).order_by(CompanySettings.created_at.desc())
        if search:
            like = f"%{search.strip()}%"
            owners = select(User.company_id).where(User.email.ilike(like))
            query = query.where(or_(CompanySettings.company_name.ilike(like), CompanySettings.id.in_(owners)))
        companies = list(await self.db.scalars(query.limit(500)))
        users = await self._count_by_company(User, User.is_active.is_(True))
        customers = await self._count_by_company(Customer)
        invoices = await self._count_by_company(Invoice)
        money = dict(
            (row[0], (row[1], row[2]))
            for row in (
                await self.db.execute(
                    select(Invoice.company_id, func.coalesce(func.sum(Invoice.total), 0), func.coalesce(func.sum(Invoice.amount_paid), 0))
                    .where(Invoice.status.in_(_BILLED))
                    .group_by(Invoice.company_id)
                )
            ).all()
        )
        last_seen = dict((await self.db.execute(select(AuditEvent.company_id, func.max(AuditEvent.created_at)).group_by(AuditEvent.company_id))).all())
        subs = {s.company_id: s for s in await self.db.scalars(select(Subscription))}
        admins = {}
        for row in await self.db.execute(select(User.company_id, User.email).where(User.role == UserRole.ADMIN).order_by(User.created_at)):
            admins.setdefault(row[0], row[1])
        out = []
        for c in companies:
            sub = subs.get(c.id)
            current = effective(sub) if sub else None
            invoiced, paid = money.get(c.id, (0, 0))
            out.append(
                {
                    "id": c.id,
                    "name": c.company_name,
                    "owner_email": admins.get(c.id),
                    "created_at": c.created_at,
                    "suspended": c.suspended_at is not None,
                    "plan": current.plan.key if current else None,
                    "state": current.state if current else None,
                    "seats": sub.seats if sub else None,
                    "trial_ends_at": sub.trial_ends_at if sub else None,
                    "mrr_cents": monthly_cents(sub) if sub else 0,
                    "users": users.get(c.id, 0),
                    "customers": customers.get(c.id, 0),
                    "invoices": invoices.get(c.id, 0),
                    "invoiced": float(invoiced),
                    "collected": float(paid),
                    "last_active_at": last_seen.get(c.id),
                }
            )
        return out

    async def company(self, company_id: uuid.UUID) -> CompanySettings:
        company = await self.db.get(CompanySettings, company_id)
        if company is None:
            raise NotFoundError("Company not found", "COMPANY_NOT_FOUND")
        return company

    async def tenant(self, company_id: uuid.UUID) -> dict:
        company = await self.company(company_id)
        summary = next(t for t in await self.tenants() if t["id"] == company_id) if company else None
        sub = await self.db.scalar(select(Subscription).where(Subscription.company_id == company_id))
        payments = list(await self.db.scalars(select(BillingPayment).where(BillingPayment.company_id == company_id).order_by(BillingPayment.paid_at.desc())))
        refunds = list(await self.db.scalars(select(BillingRefund).where(BillingRefund.company_id == company_id).order_by(BillingRefund.created_at.desc())))
        numbers = dict((await self.db.execute(select(SubscriptionInvoice.payment_id, SubscriptionInvoice.number).where(SubscriptionInvoice.company_id == company_id))).all())
        users = list(await self.db.scalars(select(User).where(User.company_id == company_id).order_by(User.created_at)))
        quotes = await self.db.scalar(select(func.count()).select_from(Quote).where(Quote.company_id == company_id))
        return {
            **summary,
            "address": company.address,
            "tax_number": company.tax_number,
            "suspended_at": company.suspended_at,
            "suspended_reason": company.suspended_reason,
            "quotes": quotes,
            "subscription": {
                "status": sub.status if sub else None,
                "plan": sub.plan if sub else None,
                "interval": sub.interval if sub else None,
                "current_period_end": sub.current_period_end if sub else None,
                "billing_email": sub.billing_email if sub else None,
                "paystack_customer_code": sub.paystack_customer_code if sub else None,
            },
            "subscription_invoices": [
                {"id": i.id, "number": i.number, "amount_cents": i.amount_cents, "is_paid": i.is_paid,
                 "manual": i.trial_subscription_id is not None, "issued_at": i.issued_at}
                for i in await self.db.scalars(select(SubscriptionInvoice).where(SubscriptionInvoice.company_id == company_id).order_by(SubscriptionInvoice.issued_at.desc()))
            ],
            "payments": [
                {
                    "id": p.id,
                    "reference": p.reference,
                    "invoice_number": numbers.get(p.id),
                    "amount_cents": p.amount_cents,
                    "plan": p.plan,
                    "interval": p.interval,
                    "seats": p.seats,
                    "paid_at": p.paid_at,
                    "refunded_cents": sum(r.amount_cents for r in refunds if r.payment_id == p.id and r.status != "failed"),
                }
                for p in payments
            ],
            "refunds": [
                {"id": r.id, "payment_id": r.payment_id, "amount_cents": r.amount_cents, "reason": r.reason, "status": r.status, "created_at": r.created_at, "by": r.created_by_email}
                for r in refunds
            ],
            "people": [{"id": u.id, "name": u.full_name, "email": u.email, "role": u.role.value, "active": u.is_active, "created_at": u.created_at} for u in users],
        }

    async def suspend(self, company_id: uuid.UUID, reason: str) -> None:
        company = await self.company(company_id)
        company.suspended_at = _now()
        company.suspended_reason = reason
        await self.db.flush()

    async def delete_company(self, company_id: uuid.UUID, confirm_name: str, admin: User) -> dict:
        """Erases a company and everything it holds (a POPIA deletion request
        or a closed account). Every table cascades from company_settings.
        The admin site's activity log keeps who did it and when; Paystack
        keeps its own record of what they paid."""
        company = await self.company(company_id)
        if confirm_name.strip() != company.company_name.strip():
            raise AppError("Type the company's name exactly as shown to confirm.", "COMPANY_NAME_MISMATCH")
        if admin.company_id == company_id:
            raise AppError("You can't delete the company your own YGT admin account belongs to.", "CANNOT_DELETE_OWN_COMPANY")
        sub = await self.db.scalar(select(Subscription).where(Subscription.company_id == company_id))
        if sub and sub.status in ("active", "past_due") and sub.paystack_subscription_code and sub.paystack_email_token:
            try:
                await paystack.disable(sub.paystack_subscription_code, sub.paystack_email_token)
            except Exception as exc:
                # Never leave a card being charged for a company that no longer exists.
                raise AppError("Couldn't stop their Paystack subscription, so nothing was deleted. Cancel it in the Paystack dashboard, then try again.", "PAYSTACK_CANCEL_FAILED") from exc
        counts = {
            "people": await self.db.scalar(select(func.count()).select_from(User).where(User.company_id == company_id)),
            "customers": await self.db.scalar(select(func.count()).select_from(Customer).where(Customer.company_id == company_id, Customer.is_prospect.is_(False))),
            "invoices": await self.db.scalar(select(func.count()).select_from(Invoice).where(Invoice.company_id == company_id)),
        }
        name = company.company_name
        await self.db.execute(sa_delete(CompanySettings).where(CompanySettings.id == company_id))
        await self.db.flush()
        logger.warning("Company %s (%s) deleted by %s: %s", name, company_id, admin.email, counts)
        return {"deleted": name, **counts}

    async def unsuspend(self, company_id: uuid.UUID) -> None:
        company = await self.company(company_id)
        company.suspended_at = None
        company.suspended_reason = None
        await self.db.flush()

    async def extend_trial(self, company_id: uuid.UUID, days: int) -> None:
        """Adds days to a trial, or puts a paying company on one (counted from
        today). A card subscription is stopped first, so they aren't charged
        during the trial; they pick a plan again when it ends."""
        sub = await self.db.scalar(select(Subscription).where(Subscription.company_id == company_id))
        if sub is None:
            raise NotFoundError("This company has no subscription", "SUBSCRIPTION_NOT_FOUND")
        paying = sub.status in ("active", "past_due")
        if paying and sub.paystack_subscription_code and sub.paystack_email_token:
            try:
                await paystack.disable(sub.paystack_subscription_code, sub.paystack_email_token)
            except Exception as exc:
                raise AppError("Couldn't stop their Paystack subscription, so they're still on their paid plan. Cancel it in the Paystack dashboard, then try again.", "PAYSTACK_CANCEL_FAILED") from exc
        if paying:
            # Forgotten, so Paystack's "subscription stopped" webhook for it
            # can't mark the trial cancelled.
            sub.paystack_subscription_code = None
            sub.paystack_email_token = None
        start = _now() if paying else max(sub.trial_ends_at or _now(), _now())
        sub.status = "trialing"
        if sub.plan not in ("hustle", "grow", "scale"):
            sub.plan = "grow"
        sub.trial_ends_at = start + timedelta(days=days)
        await self.db.flush()

    async def refund(self, payment_id: uuid.UUID, amount_cents: int | None, reason: str, admin: User) -> BillingRefund:
        payment = await self.db.get(BillingPayment, payment_id)
        if payment is None:
            raise NotFoundError("Payment not found", "PAYMENT_NOT_FOUND")
        if payment.reference.startswith("manual:"):
            raise AppError("Bank-transfer refunds must be processed through your bank", "MANUAL_REFUND_REQUIRED")
        already = await self.db.scalar(
            select(func.coalesce(func.sum(BillingRefund.amount_cents), 0)).where(BillingRefund.payment_id == payment_id, BillingRefund.status != "failed")
        )
        left = payment.amount_cents - int(already)
        amount = amount_cents or left
        if amount <= 0 or amount > left:
            raise AppError(f"You can refund at most {left / 100:.2f} on this payment", "REFUND_TOO_LARGE")
        refund = BillingRefund(company_id=payment.company_id, payment_id=payment.id, amount_cents=amount, reason=reason, created_by_email=admin.email)
        self.db.add(refund)
        await self.db.flush()
        try:
            data = await paystack.refund(payment.reference, amount if amount != payment.amount_cents else None)
        except paystack.PaystackError as exc:
            refund.status = "failed"
            await self.db.flush()
            raise AppError(f"Paystack didn't accept the refund: {exc.message}", "REFUND_FAILED")
        refund.status = "processed" if data.get("status") == "processed" else "pending"
        refund.paystack_refund_id = str(data.get("id") or "") or None
        await self.db.flush()
        return refund

    async def errors(self, company_id: uuid.UUID | None, resolved: bool | None, limit: int) -> list[ErrorLog]:
        query = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit)
        if company_id:
            query = query.where(ErrorLog.company_id == company_id)
        if resolved is not None:
            query = query.where(ErrorLog.resolved_at.is_not(None) if resolved else ErrorLog.resolved_at.is_(None))
        return list(await self.db.scalars(query))

    async def activity(self, company_id: uuid.UUID | None, search: str | None, limit: int, before: datetime | None) -> list[AuditEvent]:
        query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        if company_id:
            query = query.where(AuditEvent.company_id == company_id)
        if search:
            like = f"%{search.strip()}%"
            query = query.where(or_(AuditEvent.actor_email.ilike(like), AuditEvent.route.ilike(like)))
        if before:
            query = query.where(AuditEvent.created_at < before)
        return list(await self.db.scalars(query))

    async def company_names(self, ids) -> dict[uuid.UUID, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = await self.db.execute(select(CompanySettings.id, CompanySettings.company_name).where(CompanySettings.id.in_(ids)))
        return dict(rows.all())
