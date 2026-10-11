# YGT's own emails (help desk, Contact us, bookings, password resets), and
# failed background jobs written to the admin site's error log.
import logging
import traceback

from celery.signals import task_failure

from celery_app import celery_app

from app.services.email_service import EmailNotConfiguredError, OutgoingEmail, send_email
from app.services.platform_email import platform_config

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.platform_tasks.send_platform_email_task",
    autoretry_for=(OSError,),
    retry_backoff=30,
    retry_backoff_max=1800,
    max_retries=5,
)
def send_platform_email_task(payload: dict) -> bool:
    email = OutgoingEmail(**payload)
    try:
        send_email(platform_config(), email)
    except EmailNotConfiguredError:
        logger.warning("Skipping YGT email to %s: SMTP or SUPPORT_EMAIL is not set", email.to)
        return False
    return True


@task_failure.connect
def _record_task_failure(sender=None, task_id=None, exception=None, **_):
    """Any background job that finally fails shows up in the error log."""
    from app.core.middleware import _write
    from app.models.platform import ErrorLog
    from app.tasks._runner import run_async

    row = ErrorLog(
        source="task",
        path=getattr(sender, "name", None),
        request_id=(task_id or "")[:40],
        error_type=type(exception).__name__ if exception else "Error",
        message=f"{exception}"[:4000],
        traceback="".join(traceback.format_exception(type(exception), exception, exception.__traceback__))[-20000:] if exception else "",
    )
    try:
        run_async(lambda: _write(row))
    except Exception:
        logger.exception("Could not record failed task %s", task_id)
