import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import CUSTOM_FIELDS
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.custom_field import CustomFieldCreate, CustomFieldOut, CustomFieldUpdate, Entity
from app.services.custom_field_service import CustomFieldService

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/custom-fields", tags=["custom fields"])

_require_admin = require_role(UserRole.ADMIN)


@router.get("", response_model=list[CustomFieldOut])
async def list_custom_fields(
    entity: Entity | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Every signed-in user needs the definitions to render forms.
    return await CustomFieldService(db).list_fields(entity)


@router.post("", response_model=CustomFieldOut, status_code=201, dependencies=[Depends(plan_feature(CUSTOM_FIELDS))])
async def create_custom_field(
    data: CustomFieldCreate, db: AsyncSession = Depends(get_db), _: User = Depends(_require_admin)
):
    return await CustomFieldService(db).create_field(data)


@router.patch("/{field_id}", response_model=CustomFieldOut)
async def update_custom_field(
    field_id: uuid.UUID,
    data: CustomFieldUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_require_admin),
):
    return await CustomFieldService(db).update_field(field_id, data)


@router.delete("/{field_id}", status_code=204)
async def delete_custom_field(
    field_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_require_admin)
):
    await CustomFieldService(db).delete_field(field_id)
