import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.post("", response_model=CustomerOut, status_code=201)
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
