import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import RECURRING
from app.models.enums import UserRole
from app.models.recurring import RecurringInvoice
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.recurring import (
    RecurringInvoiceCreate,
    RecurringInvoiceDetail,
    RecurringInvoiceMade,
    RecurringInvoiceOut,
    RecurringInvoiceUpdate,
)
from app.services.recurring_service import RecurringInvoiceService, schedule_total
from app.services.reminder_service import company_today

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/recurring-invoices", tags=["recurring invoices"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)
_can_manage = require_role(UserRole.ADMIN, UserRole.MANAGER)
# Making or restarting a schedule needs Scale. Viewing, pausing and deleting
# stay open, so a company that moves to a smaller plan can still stop them.
_scale = [Depends(plan_feature(RECURRING))]


async def _today(db: AsyncSession):
    return company_today((await CompanySettingsRepository(db).get_current()).default_timezone)


def _out(schedule: RecurringInvoice, model=RecurringInvoiceOut, **extra):
    out = model.model_validate(schedule)
    out.total = schedule_total(schedule)
    for key, value in extra.items():
        setattr(out, key, value)
    return out


@router.get("", response_model=list[RecurringInvoiceOut])
async def list_recurring(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return [_out(s) for s in await RecurringInvoiceService(db).list()]


@router.get("/{schedule_id}", response_model=RecurringInvoiceDetail)
async def get_recurring(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = RecurringInvoiceService(db)
    schedule = await service.get(schedule_id)
    made = [RecurringInvoiceMade.model_validate(i) for i in await service.invoices_made(schedule_id)]
    return _out(schedule, RecurringInvoiceDetail, invoices=made)


@router.post("", response_model=RecurringInvoiceOut, status_code=status.HTTP_201_CREATED, dependencies=_scale)
async def create_recurring(
    data: RecurringInvoiceCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)
):
    """Bill a customer on a schedule. Each cycle makes a draft invoice to
    review and send; if the start date is today or earlier, the first draft
    is made now."""
    return _out(await RecurringInvoiceService(db).create(data, created_by=user.id, today=await _today(db)))


@router.patch("/{schedule_id}", response_model=RecurringInvoiceOut, dependencies=_scale)
async def update_recurring(
    schedule_id: uuid.UUID, data: RecurringInvoiceUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    return _out(await RecurringInvoiceService(db).update(schedule_id, data))


@router.post("/{schedule_id}/pause", response_model=RecurringInvoiceOut)
async def pause_recurring(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    return _out(await RecurringInvoiceService(db).set_active(schedule_id, False, await _today(db)))


@router.post("/{schedule_id}/resume", response_model=RecurringInvoiceOut, dependencies=_scale)
async def resume_recurring(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    """Switches it back on from the next cycle; cycles missed while paused are skipped."""
    return _out(await RecurringInvoiceService(db).set_active(schedule_id, True, await _today(db)))


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_manage)):
    """Stops it for good. The invoices it already made stay."""
    await RecurringInvoiceService(db).delete(schedule_id)
