import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services.payment_service import PaymentService
from app.tasks.email_tasks import send_payment_receipt_task

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["payments"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.post("/invoices/{invoice_id}/payments", response_model=PaymentOut, status_code=201)
async def record_payment(
    invoice_id: uuid.UUID,
    data: PaymentCreate,
    notify: bool = Query(True, description="Email the customer a payment receipt"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    payment = await PaymentService(db).record_payment(invoice_id, data, recorded_by_id=current_user.id)
    if notify:
        await commit_and_enqueue(db, send_payment_receipt_task, str(payment.id))
    return payment


@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentOut])
async def list_payments(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await PaymentService(db).list_payments(invoice_id)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    await PaymentService(db).delete_payment(payment_id)
