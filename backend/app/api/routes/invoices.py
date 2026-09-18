import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.enums import InvoiceStatus, UserRole
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceFromQuote, InvoiceOut, InvoiceUpdate
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["invoices"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.post("", response_model=InvoiceOut, status_code=201)
async def create_invoice(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    return await InvoiceService(db).create_invoice(data, created_by_id=current_user.id)


@router.post("/from-quote/{quote_id}", response_model=InvoiceOut, status_code=201)
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await InvoiceService(db).transition_status(invoice_id, InvoiceStatus.SENT)


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
async def void_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    return await InvoiceService(db).transition_status(invoice_id, InvoiceStatus.VOID)
