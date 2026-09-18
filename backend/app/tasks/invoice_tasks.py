import asyncio

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.services.invoice_service import InvoiceService


async def _refresh_overdue_invoices() -> int:
    async with AsyncSessionLocal() as session:
        updated = await InvoiceService(session).refresh_overdue_invoices()
        await session.commit()
        return updated


@celery_app.task(name="app.tasks.invoice_tasks.invoice_status_refresh_task")
def invoice_status_refresh_task() -> int:
    """Flips SENT/PARTIALLY_PAID invoices past their due_date to OVERDUE.
    Scheduled hourly by celery_app.conf.beat_schedule; also triggerable
    on-demand via POST /invoices/refresh-overdue."""
    return asyncio.run(_refresh_overdue_invoices())
