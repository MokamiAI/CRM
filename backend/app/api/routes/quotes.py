import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.enums import QuoteStatus, UserRole
from app.models.user import User
from app.schemas.quote import QuoteCreate, QuoteOut, QuoteUpdate
from app.services.quote_service import QuoteService

router = APIRouter(prefix="/quotes", tags=["quotes"])

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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await QuoteService(db).transition_status(quote_id, QuoteStatus.SENT)


@router.post("/{quote_id}/accept", response_model=QuoteOut)
async def accept_quote(
    quote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await QuoteService(db).transition_status(quote_id, QuoteStatus.ACCEPTED)


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
