from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "crm",
    broker=settings.REDIS_URL,
    # Results are never read back; stored only on a real Redis. Local work
    # without Redis uses REDIS_URL=memory:// (jobs accepted, not delivered).
    backend=settings.REDIS_URL if settings.REDIS_URL.startswith("redis") else None,
    include=[
        "app.tasks.billing_tasks",
        "app.tasks.discovery_tasks",
        "app.tasks.email_tasks",
        "app.tasks.invoice_tasks",
        "app.tasks.marketing_tasks",
        "app.tasks.messaging_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.platform_tasks",
        "app.tasks.recurring_tasks",
        "app.tasks.reminder_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={
        "app.tasks.email_tasks.*": {"queue": "emails"},
        "app.tasks.marketing_tasks.*": {"queue": "emails"},
        "app.tasks.messaging_tasks.*": {"queue": "emails"},
        "app.tasks.platform_tasks.*": {"queue": "emails"},
        "app.tasks.invoice_tasks.*": {"queue": "reports"},
    },
    timezone=settings.DEFAULT_TIMEZONE,
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "expired-trial-invoices": {
        "task": "app.tasks.billing_tasks.invoice_expired_trials_task",
        "schedule": crontab(minute=5),
    },
    # Yearly plans: told 40 to 80 business days before they renew (CPA s14).
    "yearly-renewal-notices": {
        "task": "app.tasks.billing_tasks.send_renewal_notices_task",
        "schedule": crontab(hour=8, minute=15),
    },
    # Sign-ups, payments and ended trials into YGT's own pipeline.
    "subscriber-pipeline": {
        "task": "app.tasks.billing_tasks.sync_subscriber_pipeline_task",
        "schedule": crontab(minute="*/5"),
    },
    # Monday morning: new potential leads, and one email per admin about them.
    "weekly-discovery": {
        "task": "app.tasks.discovery_tasks.weekly_discovery_task",
        "schedule": crontab(hour=7, minute=30, day_of_week=1),
    },
    # Every minute: activities falling due (a minute before their time) and,
    # on Monday mornings, deals with no next step.
    "due-reminders": {
        "task": "app.tasks.notification_tasks.due_reminders_task",
        "schedule": crontab(),
    },
    # Before the reminders: today's recurring drafts are ready first.
    "daily-recurring-invoices": {
        "task": "app.tasks.recurring_tasks.make_recurring_invoices_task",
        "schedule": crontab(hour=6, minute=0),
    },
    "daily-invoice-reminder": {
        "task": "app.tasks.reminder_tasks.daily_invoice_reminder_task",
        "schedule": crontab(hour=7, minute=0),
    },
    "scheduled-campaigns": {
        "task": "app.tasks.marketing_tasks.dispatch_scheduled_campaigns_task",
        "schedule": crontab(),  # every minute
    },
    "poll-company-mailboxes": {
        "task": "app.tasks.messaging_tasks.poll_mailboxes_task",
        "schedule": crontab(),  # every minute
    },
    "hourly-invoice-status-refresh": {
        "task": "app.tasks.invoice_tasks.invoice_status_refresh_task",
        "schedule": crontab(minute=0),
    },
}
