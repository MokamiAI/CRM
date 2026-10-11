"""Suppliers, purchase orders to them, and saved sets of line items."""
import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import ConflictError
from app.models.enums import PurchaseOrderStatus, UserRole
from app.models.user import User
from app.schemas.purchasing import (
    LineTemplateCreate,
    LineTemplateOut,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)
from app.services.document_service import DocumentService
from app.services.purchasing_service import LineTemplateService, PurchaseOrderService, SupplierService
from app.tasks.email_tasks import send_purchase_order_email_task

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["purchasing"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


# ---------- Suppliers ----------


@router.get("/suppliers", response_model=list[SupplierOut])
async def list_suppliers(
    search: str | None = Query(default=None, max_length=100),
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await SupplierService(db).list(search, include_inactive)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
async def create_supplier(data: SupplierCreate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await SupplierService(db).create(data)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
async def get_supplier(supplier_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await SupplierService(db).get(supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
async def update_supplier(supplier_id: uuid.UUID, data: SupplierUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await SupplierService(db).update(supplier_id, data)


# ---------- Purchase orders ----------


@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
async def list_purchase_orders(
    status_filter: PurchaseOrderStatus | None = Query(default=None, alias="status"),
    supplier_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await PurchaseOrderService(db).list(status_filter, supplier_id, offset, limit)


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(data: PurchaseOrderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    return await PurchaseOrderService(db).create(data, user.id)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
async def get_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await PurchaseOrderService(db).get(po_id)


@router.patch("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
async def update_purchase_order(po_id: uuid.UUID, data: PurchaseOrderUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await PurchaseOrderService(db).update(po_id, data)


@router.delete("/purchase-orders/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await PurchaseOrderService(db).delete(po_id)


@router.post("/purchase-orders/{po_id}/send", response_model=PurchaseOrderOut)
async def send_purchase_order(
    po_id: uuid.UUID,
    notify: bool = Query(True, description="Email the purchase order to the supplier"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    po = await PurchaseOrderService(db).transition(po_id, PurchaseOrderStatus.SENT)
    if notify:
        await commit_and_enqueue(db, send_purchase_order_email_task, str(po.id))
    return po


@router.post("/purchase-orders/{po_id}/resend", response_model=PurchaseOrderOut)
async def resend_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    po = await PurchaseOrderService(db).get(po_id)
    if po.status not in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.RECEIVED):
        raise ConflictError("Only a purchase order that has been sent can be sent again", "PURCHASE_ORDER_NOT_RESENDABLE")
    await commit_and_enqueue(db, send_purchase_order_email_task, str(po.id))
    return po


@router.post("/purchase-orders/{po_id}/receive", response_model=PurchaseOrderOut)
async def receive_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await PurchaseOrderService(db).transition(po_id, PurchaseOrderStatus.RECEIVED)


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderOut)
async def cancel_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return await PurchaseOrderService(db).transition(po_id, PurchaseOrderStatus.CANCELLED)


@router.get("/purchase-orders/{po_id}/document", response_class=HTMLResponse)
async def purchase_order_document(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return HTMLResponse(await DocumentService(db).purchase_order_html(po_id))


# ---------- Saved sets of line items ----------


@router.get("/line-templates", response_model=list[LineTemplateOut])
async def list_line_templates(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await LineTemplateService(db).list()


@router.post("/line-templates", response_model=LineTemplateOut, status_code=status.HTTP_201_CREATED)
async def save_line_template(data: LineTemplateCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    """Saving under a name that exists replaces that set."""
    return await LineTemplateService(db).create(data, user.id)


@router.delete("/line-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line_template(template_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await LineTemplateService(db).delete(template_id)
