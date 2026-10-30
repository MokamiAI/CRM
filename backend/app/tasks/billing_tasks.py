"""Issue and deliver unpaid invoices after trials expire (manual bank payments)."""
import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.plans import PLANS
from app.core.tenancy import set_system
from app.models.billing import Subscription, SubscriptionInvoice
from app.services import platform_email, subscriber_pipeline
from app.services.manual_billing import issue_trial_invoice, invoice_email
from app.services.subscription_invoices import recipients, render_html
from app.services.document_service import pdf_attachment
from app.services.email_service import send_email
from app.services.platform_email import platform_config
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)


async def invoice_expired_trials():
    if not settings.MANUAL_TRIAL_INVOICES_ENABLED:
        return 0
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        set_system(db)
        ids = list(await db.scalars(select(Subscription.id).where(Subscription.status == "trialing", Subscription.trial_ends_at <= now)))
    for sub_id in ids:
        try:
            async with AsyncSessionLocal() as db:
                set_system(db)
                await issue_trial_invoice(db, sub_id, now)
                await db.commit()
        except Exception:
            logger.exception("Could not issue trial invoice for subscription %s", sub_id)
    # Persist invoices first. Failed delivery remains pending for the next run.
    async with AsyncSessionLocal() as db:
        set_system(db)
        pending = list(await db.scalars(select(SubscriptionInvoice.id).where(
            SubscriptionInvoice.trial_subscription_id.is_not(None), SubscriptionInvoice.payment_id.is_(None), SubscriptionInvoice.emailed_at.is_(None))))
    sent = 0
    for invoice_id in pending:
        try:
            sent += int(await deliver_invoice(invoice_id, now))
        except Exception:
            logger.exception("Could not deliver trial invoice %s; delivery will retry", invoice_id)
    return sent


async def deliver_invoice(invoice_id, now=None):
    now = now or datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        set_system(db)
        invoice = await db.scalar(select(SubscriptionInvoice).where(SubscriptionInvoice.id == invoice_id,
            SubscriptionInvoice.emailed_at.is_(None), SubscriptionInvoice.payment_id.is_(None)).with_for_update(skip_locked=True))
        if invoice is None:
            return False
        sub = await db.get(Subscription, invoice.trial_subscription_id)
        if sub is None or sub.status != "trialing" or sub.trial_ends_at is None or sub.trial_ends_at > now:
            return False
        addresses = await recipients(db, invoice.company_id, sub.billing_email)
        if not addresses:
            return False
        attachment = await pdf_attachment(render_html(invoice), invoice.number)
        for address in addresses:
            email = invoice_email(invoice, address)
            if attachment:
                email = replace(email, attachments=[attachment])
            await asyncio.to_thread(send_email, platform_config(), email)
        invoice.emailed_at = datetime.now(timezone.utc)
        await db.commit()
        return True


@celery_app.task(name="app.tasks.billing_tasks.invoice_expired_trials_task")
def invoice_expired_trials_task():
    return run_async(invoice_expired_trials)


async def sync_subscriber_pipeline():
    async with AsyncSessionLocal() as db:
        changes = await subscriber_pipeline.sync(db)
        await db.commit()
    from app.tasks.email_tasks import send_invoice_email_task

    for change in changes:
        logger.info("YGT pipeline: %s %s -> %s %s", change.action, change.company, change.stage.value, change.detail)
        if change.email_invoice_id is not None:
            # A new sign-up's R0.00 trial invoice; saved above, so it can go now.
            send_invoice_email_task.delay(str(change.email_invoice_id))
    return len(changes)


@celery_app.task(name="app.tasks.billing_tasks.sync_subscriber_pipeline_task")
def sync_subscriber_pipeline_task():
    return run_async(sync_subscriber_pipeline)


# CPA s14(2)(c): a yearly plan's holder hears 40 to 80 business days before
# it renews. In calendar days, 62 to 100 sits inside that window even with
# public holidays.
RENEWAL_NOTICE_DAYS = (62, 100)


async def send_renewal_notices(now=None) -> int:
    """Once a year, to each active yearly plan's admins and billing email:
    when it renews, for how much, and how to change or cancel it."""
    now = now or datetime.now(timezone.utc)
    soonest, latest = (now + timedelta(days=d) for d in RENEWAL_NOTICE_DAYS)
    async with AsyncSessionLocal() as db:
        set_system(db)
        subs = list(await db.scalars(select(Subscription).where(
            Subscription.interval == "annually", Subscription.status == "active",
            Subscription.current_period_end >= soonest, Subscription.current_period_end <= latest)))
        sent = 0
        for sub in subs:
            plan = PLANS.get(sub.plan)
            if plan is None or sub.renewal_notice_for == sub.current_period_end:
                continue
            addresses = await recipients(db, sub.company_id, sub.billing_email)
            if not addresses:
                continue
            renews = f"{sub.current_period_end:%d %B %Y}".lstrip("0")
            amount = f"R{plan.price_cents('annually', sub.seats) / 100:,.2f}".replace(",", " ")
            emails = [
                platform_email.compose(
                    to=address,
                    subject=f"Your yearly YGT plan renews on {renews}",
                    title="Your yearly plan renews soon",
                    paragraphs=[
                        f"Your YGT {plan.name} plan renews for another year on {renews}, for {amount}.",
                        "To keep it, you don't need to do anything. To change your plan or cancel, go to Settings > Billing before that date. "
                        "If you cancel, YGT keeps working until the end of the year you've paid for.",
                    ],
                    button=("Open billing", platform_email.app_link("/settings?tab=billing")),
                )
                for address in addresses
            ]
            sub.renewal_notice_for = sub.current_period_end
            await platform_email.queue(db, *emails)  # commits
            sent += 1
    return sent


@celery_app.task(name="app.tasks.billing_tasks.send_renewal_notices_task")
def send_renewal_notices_task():
    return run_async(send_renewal_notices)
