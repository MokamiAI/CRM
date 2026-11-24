"""Credit notes: take an amount off an invoice that has gone out, even
after it has been partly paid. Managers and admins, like voiding."""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import ConflictError
from app.models.credit_note import ISSUED
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.credit_note import CreditNoteCreate, CreditNoteOut
from app.services.credit_note_service import CreditNoteService
from app.services.document_service import DocumentService
from app.tasks.email_tasks import send_credit_note_email_task

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["credit notes"])

_managers = require_role(UserRole.ADMIN, UserRole.MANAGER)


@router.get("/invoices/{invoice_id}/credit-notes", response_model=list[CreditNoteOut])
async def list_invoice_credit_notes(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = CreditNoteService(db)
    return await service.with_numbers(await service.list_for_invoice(invoice_id))


@router.post("/invoices/{invoice_id}/credit-notes", response_model=CreditNoteOut, status_code=201)
async def create_credit_note(
    invoice_id: uuid.UUID,
    data: CreditNoteCreate,
    notify: bool = Query(False, description="Email the credit note to the customer"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_managers),
):
    note = await CreditNoteService(db).create(invoice_id, data, created_by_id=user.id)
    if notify:
        await commit_and_enqueue(db, send_credit_note_email_task, str(note.id))
    return note


@router.get("/credit-notes", response_model=list[CreditNoteOut])
async def list_credit_notes(
    customer_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    service = CreditNoteService(db)
    return await service.with_numbers(await service.list_all(customer_id=customer_id))


@router.get("/credit-notes/{credit_note_id}", response_model=CreditNoteOut)
async def get_credit_note(credit_note_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = CreditNoteService(db)
    return (await service.with_numbers([await service.get(credit_note_id)]))[0]


@router.post("/credit-notes/{credit_note_id}/void", response_model=CreditNoteOut)
async def void_credit_note(credit_note_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_managers)):
    return await CreditNoteService(db).void(credit_note_id, voided_by_id=user.id)


@router.post("/credit-notes/{credit_note_id}/send", response_model=CreditNoteOut)
async def send_credit_note(
    credit_note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)),
):
    service = CreditNoteService(db)
    note = await service.get(credit_note_id)
    if note.status != ISSUED:
        raise ConflictError("A void credit note isn't sent", "CREDIT_NOTE_VOID")
    await commit_and_enqueue(db, send_credit_note_email_task, str(note.id))
    return (await service.with_numbers([note]))[0]


@router.get("/credit-notes/{credit_note_id}/document", response_class=HTMLResponse)
async def credit_note_document(credit_note_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """The credit note as a printable A4 page, styled by Settings > Documents."""
    return HTMLResponse(await DocumentService(db).credit_note_html(credit_note_id))
