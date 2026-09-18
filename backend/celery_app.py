from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "crm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.invoice_tasks",
        "app.tasks.reminder_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={
        "app.tasks.email_tasks.*": {"queue": "emails"},
        "app.tasks.invoice_tasks.*": {"queue": "reports"},
    },
    timezone=settings.DEFAULT_TIMEZONE,
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "daily-invoice-reminder": {
        "task": "app.tasks.reminder_tasks.daily_invoice_reminder_task",
        "schedule": crontab(hour=7, minute=0),
    },
    "hourly-invoice-status-refresh": {
        "task": "app.tasks.invoice_tasks.invoice_status_refresh_task",
        "schedule": crontab(minute=0),
    },
}
