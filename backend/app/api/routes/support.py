"""The Support tab: a company's tickets with YGT, and booking a session.
Open to everyone in the company, even after a trial ends."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.database import CommitBeforeResponseRoute
from app.models.user import User
from app.schemas.platform import BookingCreate, BookingOut, SlotsOut, TicketCreate, TicketDetail, TicketMessageOut, TicketOut, TicketReply
from app.services.booking_service import BookingService
from app.services.helpdesk_service import HelpdeskService

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["support"])


async def _detail(service: HelpdeskService, ticket) -> TicketDetail:
    messages = await service.messages(ticket, include_internal=False)
    return TicketDetail(**TicketOut.model_validate(ticket).model_dump(), messages=[TicketMessageOut.model_validate(m) for m in messages])


@router.get("/support/tickets", response_model=list[TicketOut])
async def my_tickets(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await HelpdeskService(db).list_mine()


@router.post("/support/tickets", response_model=TicketDetail, status_code=201)
async def open_ticket(data: TicketCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = HelpdeskService(db)
    ticket = await service.open_ticket(user, data.subject, data.category, data.urgency, data.body)
    return await _detail(service, ticket)


@router.get("/support/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = HelpdeskService(db)
    return await _detail(service, await service.get_mine(ticket_id))


@router.post("/support/tickets/{ticket_id}/messages", response_model=TicketDetail)
async def reply(ticket_id: uuid.UUID, data: TicketReply, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = HelpdeskService(db)
    ticket = await service.get_mine(ticket_id)
    await service.reply_as_company(ticket, user, data.body)
    return await _detail(service, ticket)


@router.post("/support/tickets/{ticket_id}/close", response_model=TicketDetail)
async def close(ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = HelpdeskService(db)
    ticket = await service.close_as_company(await service.get_mine(ticket_id))
    return await _detail(service, ticket)


# ---------- Book a session ----------


@router.get("/bookings/slots", response_model=SlotsOut)
async def slots(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await BookingService(db).slots()


@router.get("/bookings", response_model=list[BookingOut])
async def my_bookings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await BookingService(db).mine()


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def book(data: BookingCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await BookingService(db).book(user, data.starts_at, data.topic, data.notes)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
async def cancel(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await BookingService(db).cancel(booking_id)
