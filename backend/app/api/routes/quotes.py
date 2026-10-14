import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import ConflictError
from app.models.enums import QuoteStatus, UserRole
from app.models.user import User
from app.schemas.quote import QuoteAcceptOut, QuoteCreate, QuoteOut, QuoteUpdate
from app.services.document_service import DocumentService
from app.services.quote_service import QuoteService
from app.tasks.email_tasks import send_quote_email_task

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/quotes", tags=["quotes"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.post("", response_model=QuoteOut, status_code=201)
async def create_quote(
    data: QuoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    return await QuoteService(db).create_quote(data, created_by_id=current_user.id)


@router.get("", response_model=list[QuoteOut])
async def list_quotes(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    customer_id: uuid.UUID | None = Query(default=None),
    status_filter: QuoteStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await QuoteService(db).list_quotes(
        offset=offset, limit=limit, customer_id=customer_id, status=status_filter
    )


@router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await QuoteService(db).get_quote(quote_id)


@router.patch("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: uuid.UUID,
    data: QuoteUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await QuoteService(db).update_quote(quote_id, data)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    await QuoteService(db).delete_quote(quote_id)


@router.post("/{quote_id}/send", response_model=QuoteOut)
async def send_quote(
    quote_id: uuid.UUID,
    notify: bool = Query(True, description="Email the quote to the customer"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    quote = await QuoteService(db).transition_status(quote_id, QuoteStatus.SENT)
    if notify:
        await commit_and_enqueue(db, send_quote_email_task, str(quote.id))
    return quote


@router.post("/{quote_id}/resend", response_model=QuoteOut)
async def resend_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    """Emails a quote that has already gone out again, without changing its status."""
    quote = await QuoteService(db).get_quote(quote_id)
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.ACCEPTED):
        raise ConflictError("Only a quote that has been sent can be sent again", "QUOTE_NOT_RESENDABLE")
    await commit_and_enqueue(db, send_quote_email_task, str(quote.id))
    return quote


@router.post("/{quote_id}/revise", response_model=QuoteOut)
async def revise_quote(quote_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    """Edit for a sent quote with no answer yet: back to draft, to change
    and send again."""
    return await QuoteService(db).revise(quote_id)


@router.post("/{quote_id}/accept", response_model=QuoteAcceptOut)
async def accept_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    """Accepts the quote and makes a draft invoice from it, ready to review.
    Nothing is sent to the customer."""
    quote, invoice = await QuoteService(db).accept(quote_id, accepted_by=current_user.id)
    out = QuoteAcceptOut.model_validate(quote)
    if invoice is not None:
        out.invoice_id, out.invoice_number = invoice.id, invoice.invoice_number
    return out


@router.post("/{quote_id}/reject", response_model=QuoteOut)
async def reject_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await QuoteService(db).transition_status(quote_id, QuoteStatus.REJECTED)


@router.post("/{quote_id}/expire", response_model=QuoteOut)
async def expire_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await QuoteService(db).transition_status(quote_id, QuoteStatus.EXPIRED)


@router.get("/{quote_id}/document", response_class=HTMLResponse)
async def quote_document(quote_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """The quote as a printable A4 page, styled by Settings > Documents."""
    return HTMLResponse(await DocumentService(db).quote_html(quote_id))
