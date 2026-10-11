"""The admin site's API: YGT's own team only (PLATFORM_ADMIN_EMAILS)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_platform_admin
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import NotFoundError
from app.models.platform import ContactRequest, ErrorLog, SessionBooking, SupportTicket
from app.models.user import User
from app.schemas.platform import (
    AdminBookingOut,
    AdminTicketDetail,
    AdminTicketOut,
    AdminTicketReply,
    Availability,
    BookingOut,
    ContactOut,
    ContactUpdate,
    DeleteCompanyIn,
    ExtendTrialIn,
    RefundIn,
    SuspendIn,
    TicketMessageOut,
    TicketOut,
    TicketUpdate,
)
from app.services.admin_service import AdminService
from app.services.billing_service import effective
from app.services.booking_service import BookingService
from app.services.helpdesk_service import HelpdeskService
from app.models.billing import Subscription

router = APIRouter(
    route_class=CommitBeforeResponseRoute, prefix="/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)]
)


# ---------- Overview and tenants ----------


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    return await AdminService(db).overview()


@router.get("/tenants")
async def tenants(search: str | None = Query(default=None, max_length=100), db: AsyncSession = Depends(get_db)):
    return await AdminService(db).tenants(search)


@router.get("/tenants/{company_id}")
async def tenant(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await AdminService(db).tenant(company_id)


@router.post("/tenants/{company_id}/suspend")
async def suspend(company_id: uuid.UUID, data: SuspendIn, db: AsyncSession = Depends(get_db)):
    service = AdminService(db)
    await service.suspend(company_id, data.reason)
    return await service.tenant(company_id)


@router.post("/tenants/{company_id}/delete")
async def delete_company(
    company_id: uuid.UUID, data: DeleteCompanyIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_platform_admin)
):
    """Erases a company and all its data. Can't be undone."""
    return await AdminService(db).delete_company(company_id, data.confirm_name, admin)


@router.post("/tenants/{company_id}/unsuspend")
async def unsuspend(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    service = AdminService(db)
    await service.unsuspend(company_id)
    return await service.tenant(company_id)


@router.post("/tenants/{company_id}/extend-trial")
async def extend_trial(company_id: uuid.UUID, data: ExtendTrialIn, db: AsyncSession = Depends(get_db)):
    service = AdminService(db)
    await service.extend_trial(company_id, data.days)
    return await service.tenant(company_id)


@router.post("/payments/{payment_id}/refund")
async def refund(payment_id: uuid.UUID, data: RefundIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_platform_admin)):
    row = await AdminService(db).refund(payment_id, data.amount_cents, data.reason, admin)
    return {"id": row.id, "status": row.status, "amount_cents": row.amount_cents}


# ---------- Errors and activity ----------


def _error_out(e: ErrorLog, names: dict, full: bool = False) -> dict:
    out = {
        "id": e.id, "created_at": e.created_at, "company_id": e.company_id, "company_name": names.get(e.company_id),
        "user_id": e.user_id, "source": e.source, "request_id": e.request_id, "method": e.method, "path": e.path,
        "error_type": e.error_type, "message": e.message[:300], "resolved_at": e.resolved_at,
    }
    if full:
        out |= {"message": e.message, "traceback": e.traceback}
    return out


@router.get("/errors")
async def errors(
    company_id: uuid.UUID | None = None,
    resolved: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    service = AdminService(db)
    rows = await service.errors(company_id, resolved, limit)
    names = await service.company_names(r.company_id for r in rows)
    return [_error_out(r, names) for r in rows]


@router.get("/errors/{error_id}")
async def error(error_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await db.get(ErrorLog, error_id)
    if row is None:
        raise NotFoundError("Error not found")
    return _error_out(row, await AdminService(db).company_names([row.company_id]), full=True)


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from datetime import timezone

    row = await db.get(ErrorLog, error_id)
    if row is None:
        raise NotFoundError("Error not found")
    row.resolved_at = None if row.resolved_at else datetime.now(timezone.utc)
    await db.flush()
    return {"resolved_at": row.resolved_at}


@router.get("/activity")
async def activity(
    company_id: uuid.UUID | None = None,
    search: str | None = Query(default=None, max_length=100),
    before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    service = AdminService(db)
    rows = await service.activity(company_id, search, limit, before)
    names = await service.company_names(r.company_id for r in rows)
    return [
        {
            "id": r.id, "created_at": r.created_at, "company_id": r.company_id, "company_name": names.get(r.company_id),
            "actor_email": r.actor_email, "method": r.method, "route": r.route, "entity_id": r.entity_id,
            "status_code": r.status_code, "ip": r.ip,
        }
        for r in rows
    ]


# ---------- Help desk ----------


async def _ticket_rows(db: AsyncSession, tickets: list[SupportTicket]) -> list[AdminTicketOut]:
    names = await AdminService(db).company_names(t.company_id for t in tickets)
    people = {u.id: u for u in await db.scalars(select(User).where(User.id.in_({t.created_by for t in tickets if t.created_by})))} if tickets else {}
    subs = {s.company_id: s for s in await db.scalars(select(Subscription).where(Subscription.company_id.in_({t.company_id for t in tickets})))} if tickets else {}
    out = []
    for t in tickets:
        person = people.get(t.created_by)
        sub = subs.get(t.company_id)
        out.append(
            AdminTicketOut(
                **TicketOut.model_validate(t).model_dump(),
                **{
                    "company_id": t.company_id, "company_name": names.get(t.company_id, ""), "assigned_to": t.assigned_to,
                    "created_by_name": person.full_name if person else None, "created_by_email": person.email if person else None,
                    "plan": effective(sub).plan.key if sub else None,
                },
            )
        )
    return out


@router.get("/tickets", response_model=list[AdminTicketOut])
async def tickets(status: str | None = None, company_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    query = select(SupportTicket)
    if status == "active":
        query = query.where(SupportTicket.status.in_(("open", "in_progress", "waiting")))
    elif status:
        query = query.where(SupportTicket.status == status)
    if company_id:
        query = query.where(SupportTicket.company_id == company_id)
    # Priority support first, then whatever has waited longest for YGT.
    query = query.order_by(SupportTicket.priority_plan.desc(), SupportTicket.last_from_platform, SupportTicket.last_message_at).limit(500)
    return await _ticket_rows(db, list(await db.scalars(query)))


async def _admin_detail(db: AsyncSession, ticket: SupportTicket) -> AdminTicketDetail:
    (row,) = await _ticket_rows(db, [ticket])
    messages = await HelpdeskService(db).messages(ticket, include_internal=True)
    return AdminTicketDetail(**row.model_dump(), messages=[TicketMessageOut.model_validate(m) for m in messages])


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetail)
async def ticket(ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _admin_detail(db, await HelpdeskService(db).admin_get(ticket_id))


@router.post("/tickets/{ticket_id}/messages", response_model=AdminTicketDetail)
async def reply(ticket_id: uuid.UUID, data: AdminTicketReply, db: AsyncSession = Depends(get_db), admin: User = Depends(require_platform_admin)):
    service = HelpdeskService(db)
    ticket = await service.admin_get(ticket_id)
    await service.reply_as_team(ticket, admin, data.body, data.internal)
    return await _admin_detail(db, ticket)


@router.patch("/tickets/{ticket_id}", response_model=AdminTicketDetail)
async def update_ticket(ticket_id: uuid.UUID, data: TicketUpdate, db: AsyncSession = Depends(get_db)):
    service = HelpdeskService(db)
    ticket = await service.update(await service.admin_get(ticket_id), data.status, data.urgency, data.assigned_to)
    return await _admin_detail(db, ticket)


# ---------- Contact us ----------


@router.get("/contact", response_model=list[ContactOut])
async def contact_requests(status: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(ContactRequest).order_by(ContactRequest.created_at.desc()).limit(500)
    if status:
        query = query.where(ContactRequest.status == status)
    return list(await db.scalars(query))


@router.patch("/contact/{request_id}", response_model=ContactOut)
async def update_contact(request_id: uuid.UUID, data: ContactUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(ContactRequest, request_id)
    if row is None:
        raise NotFoundError("Not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.flush()
    return row


# ---------- Sessions ----------


def _booking(row: SessionBooking, names: dict) -> AdminBookingOut:
    return AdminBookingOut(**BookingOut.model_validate(row).model_dump(), company_id=row.company_id, company_name=names.get(row.company_id, ""))


@router.get("/bookings", response_model=list[AdminBookingOut])
async def bookings(upcoming: bool = True, db: AsyncSession = Depends(get_db)):
    from datetime import timezone

    query = select(SessionBooking)
    if upcoming:
        query = query.where(SessionBooking.starts_at >= datetime.now(timezone.utc)).order_by(SessionBooking.starts_at)
    else:
        query = query.order_by(SessionBooking.starts_at.desc())
    rows = list(await db.scalars(query.limit(500)))
    names = await AdminService(db).company_names(r.company_id for r in rows)
    return [_booking(r, names) for r in rows]


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingOut)
async def cancel_booking(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    row = await BookingService(db).cancel(booking_id, by_team=True)
    names = await AdminService(db).company_names([row.company_id])
    return _booking(row, names)


@router.get("/booking-settings", response_model=Availability)
async def booking_settings(db: AsyncSession = Depends(get_db)):
    return await BookingService(db).availability()


@router.put("/booking-settings", response_model=Availability)
async def save_booking_settings(data: Availability, db: AsyncSession = Depends(get_db)):
    return await BookingService(db).save_availability(data)
