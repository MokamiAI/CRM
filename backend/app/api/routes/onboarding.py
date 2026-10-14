"""Get started checklist: what a new company still has to set up, worked
out from its real data, so items tick themselves off as people use the app."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.crm import Deal
from app.models.customer import Customer
from app.models.enums import InvoiceStatus, QuoteStatus, UserRole
from app.models.invoice import Invoice
from app.models.quote import Quote
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/onboarding", tags=["onboarding"])


class ChecklistItem(BaseModel):
    key: str
    done: bool
    optional: bool = False
    admin_only: bool = False


class Checklist(BaseModel):
    items: list[ChecklistItem]
    dismissed: bool


async def _any(db: AsyncSession, query) -> bool:
    return bool(await db.scalar(select(exists(query))))


@router.get("", response_model=Checklist)
async def checklist(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    company = await CompanySettingsRepository(db).get_current()
    sent_quote = select(Quote.id).where(Quote.status != QuoteStatus.DRAFT)
    sent_invoice = select(Invoice.id).where(Invoice.status != InvoiceStatus.DRAFT)
    # Six steps, the ones that get a company invoicing; the rest is in Help.
    items = [
        ChecklistItem(key="company", admin_only=True, done=bool(company.address)),
        ChecklistItem(key="email", admin_only=True, done=bool(company.sender_email)),
        ChecklistItem(key="customer", done=await _any(db, select(Customer.id))),
        ChecklistItem(key="deal", done=await _any(db, select(Deal.id))),
        ChecklistItem(key="send", done=await _any(db, sent_quote) or await _any(db, sent_invoice)),
        ChecklistItem(key="team", admin_only=True, done=(await db.scalar(select(func.count()).select_from(User))) > 1),
    ]
    return Checklist(items=items, dismissed=company.onboarding_dismissed_at is not None)


@router.post("/dismiss", response_model=Checklist, dependencies=[Depends(require_role(UserRole.ADMIN))])
async def dismiss(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    company = await CompanySettingsRepository(db).get_current()
    company.onboarding_dismissed_at = datetime.now(timezone.utc)
    await db.flush()
    return await checklist(db, user)
