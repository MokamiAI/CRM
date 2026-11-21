# Every five minutes (celery_app.conf.beat_schedule, "online-payments"):
# confirms online invoice payments nobody came back from, for companies
# that haven't set up Paystack's webhook or whose customer closed the tab.
from celery_app import celery_app

from app.services.online_payment_service import check_pending
from app.tasks._runner import run_async


@celery_app.task(name="app.tasks.payment_tasks.check_online_payments_task")
def check_online_payments_task() -> int:
    return run_async(check_pending)
