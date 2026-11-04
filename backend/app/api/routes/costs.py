"""Costs and recurring bills. The business's spending (salaries among it) is
for admins and managers only."""
import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, plan_feature, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import REPORTS
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.cost import (
    CostCreate,
    CostFromPurchaseOrder,
    CostList,
    CostOut,
    CostPaid,
    CostStatus,
    CostUpdate,
    MoneyOverview,
    MoneySummary,
    RecurringCostCreate,
    RecurringCostOut,
    RecurringCostUpdate,
)
from app.services.attachment_service import MAX_BYTES
from app.services.cost_service import CostService, RecurringCostService
from app.services.reminder_service import company_today

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["costs"])

_money = require_role(UserRole.ADMIN, UserRole.MANAGER)


async def _company(db: AsyncSession):
    company = await CompanySettingsRepository(db).get_current()
    return company_today(company.default_timezone), company.default_timezone


async def _today(db: AsyncSession) -> date:
    return (await _company(db))[0]


# ---------- Costs ----------


@router.get("/costs", response_model=CostList)
async def list_costs(
    status_: CostStatus | None = Query(default=None, alias="status"),
    category: str | None = None,
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_money),
):
    """Costs, newest first. Paid ones filter by the day they were paid, bills by their due date."""
    items, total_paid, total_due = await CostService(db).list(status_, category, start, end)
    return CostList(items=items, total_paid=total_paid, total_due=total_due)


@router.get("/costs/categories", response_model=list[str])
async def cost_categories(db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).categories()


@router.get("/costs/summary", response_model=MoneySummary)
async def money_summary(month: str | None = None, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    """A month's money in (payments received), money out (costs paid) and profit."""
    today, tz = await _company(db)
    return await CostService(db).summary(month or f"{today:%Y-%m}", today, tz)


@router.get("/costs/overview", response_model=MoneyOverview, dependencies=[Depends(plan_feature(REPORTS))])
async def money_overview(db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    """The Money dashboard (Grow and Scale): 12 months of money in, money out
    and profit, where the money went, and what's still to come in and to pay."""
    today, tz = await _company(db)
    return await CostService(db).overview(today, tz)


@router.post("/costs", response_model=CostOut, status_code=status.HTTP_201_CREATED)
async def create_cost(data: CostCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_money)):
    return await CostService(db).create(data, user, await _today(db))


@router.get("/costs/{cost_id}", response_model=CostOut)
async def get_cost(cost_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).get(cost_id)


@router.patch("/costs/{cost_id}", response_model=CostOut)
async def update_cost(cost_id: uuid.UUID, data: CostUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).update(cost_id, data)


@router.post("/costs/{cost_id}/paid", response_model=CostOut)
async def mark_cost_paid(cost_id: uuid.UUID, data: CostPaid, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).set_paid(cost_id, True, data.paid_date, await _today(db))


@router.post("/costs/{cost_id}/unpaid", response_model=CostOut)
async def mark_cost_unpaid(cost_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).set_paid(cost_id, False, None, await _today(db))


@router.delete("/costs/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cost(cost_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    await CostService(db).delete(cost_id)


@router.post("/costs/{cost_id}/receipt", response_model=CostOut)
async def add_receipt(cost_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    """A photo or PDF of the slip (10 MB max); replaces any earlier one."""
    return await CostService(db).add_receipt(cost_id, file.filename, await file.read(MAX_BYTES + 1))


@router.get("/costs/{cost_id}/receipt", include_in_schema=False)
async def download_receipt(cost_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    cost = await CostService(db).get(cost_id, with_receipt=True)
    if not cost.receipt_data:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(
        cost.receipt_data,
        media_type=cost.receipt_type,
        headers={
            # Always a download: an uploaded file never runs as part of the app.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(cost.receipt_name or 'receipt')}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/costs/{cost_id}/receipt", response_model=CostOut)
async def remove_receipt(cost_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await CostService(db).remove_receipt(cost_id)


@router.get("/costs/from-purchase-order/{po_id}", response_model=CostOut | None)
async def cost_for_purchase_order(po_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    """The cost a purchase order was recorded as, if it was."""
    return await CostService(db).for_purchase_order(po_id)


@router.post("/costs/from-purchase-order/{po_id}", response_model=CostOut, status_code=status.HTTP_201_CREATED)
async def cost_from_purchase_order(
    po_id: uuid.UUID, data: CostFromPurchaseOrder, db: AsyncSession = Depends(get_db), user: User = Depends(_money)
):
    """Record a sent or received purchase order as a cost, once."""
    return await CostService(db).from_purchase_order(po_id, data, user, await _today(db))


# ---------- Recurring bills ----------


@router.get("/recurring-costs", response_model=list[RecurringCostOut])
async def list_recurring_costs(db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await RecurringCostService(db).list()


@router.post("/recurring-costs", response_model=RecurringCostOut, status_code=status.HTTP_201_CREATED)
async def create_recurring_cost(data: RecurringCostCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_money)):
    """A bill that comes back. Each cycle's bill appears a week before it's due."""
    return await RecurringCostService(db).create(data, user, await _today(db))


@router.patch("/recurring-costs/{schedule_id}", response_model=RecurringCostOut)
async def update_recurring_cost(
    schedule_id: uuid.UUID, data: RecurringCostUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_money)
):
    return await RecurringCostService(db).update(schedule_id, data, await _today(db))


@router.post("/recurring-costs/{schedule_id}/pause", response_model=RecurringCostOut)
async def pause_recurring_cost(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await RecurringCostService(db).set_active(schedule_id, False, await _today(db))


@router.post("/recurring-costs/{schedule_id}/resume", response_model=RecurringCostOut)
async def resume_recurring_cost(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    return await RecurringCostService(db).set_active(schedule_id, True, await _today(db))


@router.delete("/recurring-costs/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_cost(schedule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_money)):
    await RecurringCostService(db).delete(schedule_id)
