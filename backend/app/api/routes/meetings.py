import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.crm import Activity
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.meeting import CalendarBlock, MeetingContactOut, MeetingOut, MeetingReview
from app.services.meeting_service import MeetingService, meeting_ics

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/meetings", tags=["meetings"])
_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


@router.get("/contact", response_model=MeetingContactOut)
async def meeting_contact(deal_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None, contact_id: uuid.UUID | None = None,
                          db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await MeetingService(db).contact(deal_id=deal_id, customer_id=customer_id, contact_id=contact_id)


@router.get("/calendar", response_model=list[CalendarBlock])
async def meeting_calendar(start: date, end: date, mine: bool = True, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await MeetingService(db).calendar(start, end, user, mine)


@router.post("/{activity_id}/proposal", response_model=MeetingOut)
async def review_proposal(activity_id: uuid.UUID, data: MeetingReview, db: AsyncSession = Depends(get_db), user: User = Depends(_write)):
    return await MeetingService(db).review(activity_id, data.accept, data.reason, user)


@router.post("/{activity_id}/cancel", response_model=MeetingOut)
async def cancel_meeting(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_write)):
    return await MeetingService(db).cancel(activity_id, user)


@router.get("/{activity_id}/calendar.ics")
async def download_meeting(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    meeting = await MeetingService(db).get(activity_id)
    activity = await db.get(Activity, activity_id)
    organizer = await db.get(User, meeting.organizer_id)
    return Response(meeting_ics(meeting, activity, organizer, cancel=meeting.status in ("declined", "cancelled")),
                    media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="meeting.ics"', "Cache-Control": "no-store"})
