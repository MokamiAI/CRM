import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_room, require_role
from app.api.email_dispatch import commit_and_enqueue, commit_and_enqueue_each
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import ConflictError
from app.models.enums import InvoiceStatus, UserRole
from app.models.reminder import ReminderLog
from app.models.user import User
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceFromQuote,
    InvoiceOut,
    InvoiceUpdate,
    OverdueRefreshResult,
    ReminderOut,
    RemindersQueued,
)
from app.services.document_service import DocumentService
from app.services.invoice_service import InvoiceService
from app.services.reminder_service import ReminderService
from app.tasks.email_tasks import send_invoice_email_task, send_invoice_reminder_task

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/invoices", tags=["invoices"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)
_invoice_room = Depends(plan_room("invoices_this_month"))


@router.post("", response_model=InvoiceOut, status_code=201, dependencies=[_invoice_room])
async def create_invoice(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    return await InvoiceService(db).create_invoice(data, created_by_id=current_user.id)


@router.post("/from-quote/{quote_id}", response_model=InvoiceOut, status_code=201, dependencies=[_invoice_room])
async def create_invoice_from_quote(
    quote_id: uuid.UUID,
    data: InvoiceFromQuote,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    return await InvoiceService(db).create_from_quote(quote_id, data, created_by_id=current_user.id)


@router.get("", response_model=list[InvoiceOut])
async def list_invoices(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    customer_id: uuid.UUID | None = Query(default=None),
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await InvoiceService(db).list_invoices(
        offset=offset, limit=limit, customer_id=customer_id, status=status_filter
    )


@router.post("/refresh-overdue", response_model=OverdueRefreshResult)
async def refresh_overdue_invoices(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    updated = await InvoiceService(db).refresh_overdue_invoices()
    return OverdueRefreshResult(updated=updated)


@router.post("/send-reminders", response_model=RemindersQueued)
async def send_due_reminders(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Runs the daily reminder pass now (the same logic Celery beat runs at
    07:00). Safe to repeat: each schedule step is sent at most once."""
    claimed = await ReminderService(db).claim_due_reminders()
    await commit_and_enqueue_each(
        db, send_invoice_reminder_task, [(str(r.invoice_id),) for r in claimed]
    )
    return RemindersQueued(queued=len(claimed))


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await InvoiceService(db).get_invoice(invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
async def update_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await InvoiceService(db).update_invoice(invoice_id, data)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    await InvoiceService(db).delete_invoice(invoice_id)


@router.post("/{invoice_id}/send", response_model=InvoiceOut)
async def send_invoice(
    invoice_id: uuid.UUID,
    notify: bool = Query(True, description="Email the invoice to the customer"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    invoice = await InvoiceService(db).transition_status(invoice_id, InvoiceStatus.SENT)
    if notify:
        await commit_and_enqueue(db, send_invoice_email_task, str(invoice.id))
    return invoice


_RESENDABLE = {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE, InvoiceStatus.PAID}


@router.post("/{invoice_id}/resend", response_model=InvoiceOut)
async def resend_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    """Emails an invoice that has already gone out again ("please resend"),
    without changing its status."""
    invoice = await InvoiceService(db).get_invoice(invoice_id)
    if invoice.status not in _RESENDABLE:
        raise ConflictError("Only an invoice that has been sent can be sent again", "INVOICE_NOT_RESENDABLE")
    await commit_and_enqueue(db, send_invoice_email_task, str(invoice.id))
    return invoice


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
async def void_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    return await InvoiceService(db).transition_status(invoice_id, InvoiceStatus.VOID)


@router.post("/{invoice_id}/remind", response_model=ReminderOut, status_code=202)
async def send_reminder_now(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    claimed = await ReminderService(db).claim_manual_reminder(invoice_id)
    log = await db.get(ReminderLog, claimed.log_id)
    await commit_and_enqueue(db, send_invoice_reminder_task, str(invoice_id))
    return log


@router.get("/{invoice_id}/reminders", response_model=list[ReminderOut])
async def list_reminders(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await ReminderService(db).history(invoice_id)


@router.get("/{invoice_id}/document", response_class=HTMLResponse)
async def invoice_document(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """The invoice as a printable A4 page, styled by Settings > Documents."""
    return HTMLResponse(await DocumentService(db).invoice_html(invoice_id))
