from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import REPORTS
from app.models.user import User
from app.schemas.report import AgedReceivables, CustomerOverview, ReportSummary
from app.services.report_service import ReportService

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummary)
async def summary(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Sales dashboard numbers: pipeline by stage, won this month, win
    rate, receivables, cash collected per month, top deals, recent feed."""
    return await ReportService(db).summary()


@router.get("/aged-receivables", response_model=AgedReceivables, dependencies=[Depends(plan_feature(REPORTS))])
async def aged_receivables(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """What each customer owes on sent invoices, by days past due:
    not yet due, 1-30, 31-60, 61-90 and over 90 days."""
    return await ReportService(db).aged_receivables()


@router.get("/customers", response_model=list[CustomerOverview])
async def customer_overview(
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Customers with CRM list columns: primary contact, open deals,
    pipeline value, balance owed, overdue count, last touchpoint."""
    return await ReportService(db).customer_overview(search=search, is_active=is_active)
