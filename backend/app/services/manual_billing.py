"""Unpaid invoices for expired trials; EFT payment is confirmed by YGT staff."""
import calendar
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.plans import PLANS
from app.models.billing import BillingPayment, Subscription, SubscriptionInvoice
from app.models.company_settings import CompanySettings
from app.models.user import User
from app.services import platform_email, subscription_invoices as invoices

REQUIRED_DETAILS = ("legal_name", "address", "registration_number", "email", "bank_name", "account_holder", "account_number", "branch_code")


def period_end(start, interval):
    months = 12 if interval == "annually" else 1
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


async def issue_trial_invoice(db, subscription_id, now=None):
    now = now or datetime.now(timezone.utc)
    sub = await db.scalar(select(Subscription).where(Subscription.id == subscription_id).with_for_update())
    if sub is None or sub.status != "trialing" or not sub.trial_ends_at or sub.trial_ends_at > now or sub.paystack_subscription_code:
        return None
    existing = await db.scalar(select(SubscriptionInvoice.id).where(SubscriptionInvoice.trial_subscription_id == sub.id))
    if existing:
        return None
    seller = await invoices.get_details(db)
    missing = [key for key in REQUIRED_DETAILS if not seller.get(key)]
    if missing:
        raise ConflictError("Configure YGT billing details before invoicing: " + ", ".join(missing), "BILLING_DETAILS_MISSING")
    plan = PLANS.get(sub.plan)
    if plan is None:
        raise ConflictError("Choose a valid subscription plan before invoicing", "BILLING_PLAN_INVALID")
    company = await db.get(CompanySettings, sub.company_id)
    if company is None or company.suspended_at is not None:
        return None
    # Trial seat allowances are not the number of paid users. Charge actual
    # active users, using the plan's existing per-seat/team pricing.
    count = await db.scalar(select(func.count()).select_from(User).where(User.company_id == sub.company_id, User.is_active.is_(True)))
    seats = max(plan.min_users, count) if plan.per_user else 1
    amount = plan.price_cents(sub.interval, seats)
    number = await invoices._next_number(db)
    invoice = SubscriptionInvoice(
        company_id=sub.company_id, number=number, payment_id=None,
        trial_subscription_id=sub.id, payment_reference=number, issued_at=now,
        plan=sub.plan, interval=sub.interval, seats=seats,
        period_start=now, period_end=period_end(now, sub.interval),
        amount_cents=amount, vat_cents=invoices._vat_inside(amount) if seller.get("vat_number") else 0,
        seller=seller, buyer={"name": company.company_name, "address": company.address,
            "vat_number": company.tax_number if company.vat_registered else None},
    )
    db.add(invoice)
    await db.flush()
    return invoice


def invoice_email(invoice, address):
    seller = invoice.seller
    total = f"R {invoice.amount_cents / 100:,.2f}"
    return platform_email.compose(
        to=address, subject=f"Your YGT invoice {invoice.number}: payment due",
        title="Your free trial has ended",
        paragraphs=["Your free trial has ended. To continue with your selected YGT plan, please pay the attached subscription invoice by bank transfer.",
            "Your subscription is activated after YGT confirms receipt of your payment. Your information remains saved.",
            "Use the invoice number as your payment reference. Please send proof of payment to " + seller["email"] + "."],
        details=[("Invoice", invoice.number), ("Plan", invoices.plan_label(invoice)), ("Amount due", total),
            ("Due", "On receipt"), ("Business", seller["legal_name"]), ("Registration", seller["registration_number"]),
            ("Address", seller["address"]), ("Bank", seller["bank_name"]), ("Account holder", seller["account_holder"]),
            ("Account number", seller["account_number"]), ("Branch code", seller["branch_code"]),
            ("Payment reference", invoice.number)],
        button=("View invoice", platform_email.app_link("/settings?tab=billing")),
    )


async def confirm_payment(db, invoice_id, now=None):
    now = now or datetime.now(timezone.utc)
    invoice = await db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.id == invoice_id).with_for_update())
    if invoice is None:
        raise NotFoundError("Invoice not found", "INVOICE_NOT_FOUND")
    if invoice.trial_subscription_id is None:
        raise ConflictError("This invoice is not awaiting a bank transfer", "NOT_MANUAL_INVOICE")
    if invoice.is_paid:
        return {"confirmed": True, "invoice_number": invoice.number}
    sub = await db.scalar(select(Subscription).where(Subscription.id == invoice.trial_subscription_id).with_for_update())
    if sub is None or sub.status in ("active", "past_due"):
        raise ConflictError("Review this account's existing subscription before confirming payment", "SUBSCRIPTION_ALREADY_ACTIVE")
    payment = BillingPayment(company_id=invoice.company_id, reference=f"manual:{invoice.id}", amount_cents=invoice.amount_cents,
        currency="ZAR", plan=invoice.plan, interval=invoice.interval, seats=invoice.seats, paid_at=now)
    db.add(payment)
    await db.flush()
    invoice.payment_id = payment.id
    sub.plan, sub.interval, sub.seats, sub.status = invoice.plan, invoice.interval, invoice.seats, "active"
    sub.trial_ends_at = None
    sub.current_period_end = period_end(now, invoice.interval)
    invoice.period_start, invoice.period_end = now, sub.current_period_end
    await db.flush()
    return {"confirmed": True, "invoice_number": invoice.number}
