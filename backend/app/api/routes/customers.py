import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_room, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.api.email_dispatch import commit_and_enqueue
from app.core.exceptions import AppError
from app.schemas.documents import StatementOut, StatementSend
from app.services.customer_service import CustomerService
from app.services.document_service import DocumentService
from app.tasks.email_tasks import send_statement_email_task

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/customers", tags=["customers"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.post("", response_model=CustomerOut, status_code=201, dependencies=[Depends(plan_room("customers"))])
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_can_write),
):
    return await CustomerService(db).create_customer(data, created_by=current_user)


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await CustomerService(db).list_customers(
        offset=offset, limit=limit, search=search, is_active=is_active
    )


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await CustomerService(db).get_customer(customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_can_write),
):
    return await CustomerService(db).update_customer(customer_id, data)


@router.post("/{customer_id}/deactivate", response_model=CustomerOut)
async def deactivate_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN, UserRole.MANAGER)),
):
    return await CustomerService(db).deactivate_customer(customer_id)



# ---------- Statements ----------


def _period(start: date, end: date) -> None:
    if start > end:
        raise AppError("The start date must be before the end date", "STATEMENT_PERIOD_INVALID")


@router.get("/{customer_id}/statement", response_model=StatementOut)
async def customer_statement(
    customer_id: uuid.UUID, start: date, end: date, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    _period(start, end)
    *_, statement = await DocumentService(db).statement(customer_id, start, end)
    return statement


@router.get("/{customer_id}/statement/document", response_class=HTMLResponse)
async def customer_statement_document(
    customer_id: uuid.UUID, start: date, end: date, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    _period(start, end)
    return HTMLResponse(await DocumentService(db).statement_html(customer_id, start, end))


@router.post("/{customer_id}/statement/send", status_code=202)
async def send_customer_statement(
    customer_id: uuid.UUID, data: StatementSend, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    """Emails the statement to the contact person's email address."""
    _period(data.start, data.end)
    customer = await CustomerService(db).get_customer(customer_id)
    if not customer.recipient_email:
        raise AppError("Contact person's email not found. Add an email to their contact details.", "CUSTOMER_NO_EMAIL")
    await commit_and_enqueue(db, send_statement_email_task, str(customer_id), data.start.isoformat(), data.end.isoformat())
    return {"sent_to": customer.recipient_email}
