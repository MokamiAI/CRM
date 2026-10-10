# Celery tasks that email customers when an invoice or quote is sent, or a
# payment is recorded. Enqueued by the API routes after the request's DB
# transaction commits (see app/api/routes/invoices.py, quotes.py,
# payments.py), and payment reminders queued by app/tasks/reminder_tasks.py.
import logging
import uuid
from collections.abc import Awaitable, Callable

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.services.email_service import EmailNotConfiguredError, OutgoingEmail, send_email
from app.services.email_settings import EffectiveEmailConfig
from app.services.notification_service import NotificationService
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)

# OSError covers smtplib.SMTPException and socket/TLS failures: a mail
# server that's briefly down or rate-limiting is worth retrying with
# backoff. A missing SMTP configuration is not, so it's handled below.
_RETRY_OPTIONS = {
    "autoretry_for": (OSError,),
    "retry_backoff": 30,
    "retry_backoff_max": 30 * 60,
    "max_retries": 5,
}

_Composer = Callable[[NotificationService], Awaitable[OutgoingEmail | None]]


def _deliver(compose: _Composer, description: str) -> bool:
    async def _load() -> tuple[EffectiveEmailConfig, OutgoingEmail | None]:
        async with AsyncSessionLocal() as session:
            set_system(session)
            service = NotificationService(session)
            # Compose first: it adopts the record's company, whose email
            # settings are then the ones to send with.
            email = await compose(service)
            return await service.email_config(), email

    config, email = run_async(_load)
    if email is None:
        logger.info("Skipping %s email: customer has no email address", description)
        return False
    try:
        send_email(config, email)
    except EmailNotConfiguredError:
        logger.warning("Skipping %s email: outgoing email is not configured", description)
        return False
    logger.info("Sent %s email to %s", description, email.to)
    return True


@celery_app.task(name="app.tasks.email_tasks.send_invoice_email_task", **_RETRY_OPTIONS)
def send_invoice_email_task(invoice_id: str) -> bool:
    return _deliver(
        lambda service: service.compose_invoice_sent(uuid.UUID(invoice_id)),
        f"invoice {invoice_id}",
    )


@celery_app.task(name="app.tasks.email_tasks.send_quote_email_task", **_RETRY_OPTIONS)
def send_quote_email_task(quote_id: str) -> bool:
    return _deliver(
        lambda service: service.compose_quote_sent(uuid.UUID(quote_id)),
        f"quote {quote_id}",
    )


@celery_app.task(name="app.tasks.email_tasks.send_invoice_reminder_task", **_RETRY_OPTIONS)
def send_invoice_reminder_task(invoice_id: str) -> bool:
    return _deliver(
        lambda service: service.compose_invoice_reminder(uuid.UUID(invoice_id)),
        f"reminder for invoice {invoice_id}",
    )


@celery_app.task(name="app.tasks.email_tasks.send_payment_receipt_task", **_RETRY_OPTIONS)
def send_payment_receipt_task(payment_id: str) -> bool:
    return _deliver(
        lambda service: service.compose_payment_receipt(uuid.UUID(payment_id)),
        f"payment receipt {payment_id}",
    )



@celery_app.task(name="app.tasks.email_tasks.send_statement_email_task", **_RETRY_OPTIONS)
def send_statement_email_task(customer_id: str, start: str, end: str) -> bool:
    from datetime import date

    return _deliver(
        lambda service: service.compose_statement(uuid.UUID(customer_id), date.fromisoformat(start), date.fromisoformat(end)),
        f"statement for {customer_id}",
    )
