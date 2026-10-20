from datetime import datetime
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.api.deps import get_db
from app.api.routes.public import _page
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import AppError
from app.models.crm import Activity
from app.models.user import User
from app.services.meeting_service import MeetingService, meeting_ics

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/public/meetings", tags=["meeting responses"])


async def response_page(db, meeting, error=None, status_code=200):
    activity = await db.get(Activity, meeting.activity_id)
    organizer = await db.get(User, meeting.organizer_id)
    start = meeting.starts_at.astimezone(ZoneInfo(meeting.timezone))
    body = '<style>main{overflow-wrap:anywhere}input,textarea,button{max-width:100%}textarea{font:inherit;padding:8px}label{display:block;line-height:1.5}</style>'
    body += f'<h1>{escape(activity.subject)}</h1><p>With {escape(organizer.full_name)}<br>{start:%A %d %B %Y, %H:%M} ({escape(meeting.timezone)})</p>'
    if error:
        body += f'<p role="alert" style="padding:12px;background:#fef2f2;color:#991b1b;border-radius:8px">{escape(error)}</p>'
    if meeting.location:
        body += f'<p>Location / call link: {escape(meeting.location)}</p>'
    if activity.note:
        body += f'<p style="white-space:pre-line">{escape(activity.note)}</p>'
    if meeting.status == "invited":
        body += '''<p>Choose your response below to update the organiser's calendar.</p>
<form method="post"><input type="hidden" name="action" value="accept"><button type="submit">Accept meeting</button></form>
<hr style="border:0;border-top:1px solid #eee;margin:24px 0">
<form method="post"><input type="hidden" name="action" value="decline">
<label>Reason for declining <textarea name="reason" required maxlength="2000" rows="3" style="display:block;width:100%;margin:8px 0;box-sizing:border-box"></textarea></label>
<button type="submit">Decline meeting</button></form>
<hr style="border:0;border-top:1px solid #eee;margin:24px 0">
<form method="post"><input type="hidden" name="action" value="propose">
<label>Suggest another date and time <input type="datetime-local" name="proposed_start" required style="display:block;padding:10px;margin:8px 0"></label>'''
        body += f'<p>Enter the proposed time in {escape(meeting.timezone)}. The duration stays the same.</p>'
        body += '''<label>Note (optional)<textarea name="reason" maxlength="2000" rows="2" style="display:block;width:100%;margin:8px 0;box-sizing:border-box"></textarea></label>
<button type="submit">Suggest this time</button></form>'''
    else:
        label = {"accepted": "Meeting accepted", "declined": "Meeting declined", "proposed": "New time suggested", "cancelled": "Meeting cancelled"}[meeting.status]
        body += f'<h2>{label}</h2>'
        if meeting.response_reason:
            body += f'<p>{escape(meeting.response_reason)}</p>'
        if meeting.proposed_start:
            proposed = meeting.proposed_start.astimezone(ZoneInfo(meeting.timezone))
            body += f'<p>Suggested: {proposed:%d %b %Y %H:%M} ({escape(meeting.timezone)}). This time is held tentatively in YGT while the organiser reviews it. The original time is held until a decision is made.</p>'
        body += '<p>Your response is recorded. Contact the organiser if you need to change it.</p>'
    if meeting.status not in ("cancelled", "declined"):
        body += '<p><a href="' + escape(str(meeting._response_path)) + '/calendar.ics' + ('?proposed=true' if meeting.proposed_start else '') + '">Add ' + ('the proposed time' if meeting.proposed_start else 'the meeting') + ' to your calendar</a></p><p>Your calendar app may ask you to confirm adding the event.</p>'
    result = _page("Meeting response", body)
    result.status_code = status_code
    result.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return result


@router.get("/{token}", include_in_schema=False)
async def meeting_response_page(token: str, db: AsyncSession = Depends(get_db)):
    try:
        meeting = await MeetingService(db).linked(token)
    except AppError as error:
        result = _page("Meeting link", f"<h1>Use the latest invitation</h1><p>{escape(error.message)}</p>")
        result.status_code = error.status_code
        result.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        return result
    meeting._response_path = token
    return await response_page(db, meeting)


@router.post("/{token}", include_in_schema=False)
async def meeting_response(token: str, action: Literal["accept", "decline", "propose"] = Form(...), reason: str = Form("", max_length=2000),
                           proposed_start: datetime | None = Form(None), db: AsyncSession = Depends(get_db)):
    service = MeetingService(db)
    meeting = await service.linked(token, lock=True)
    try:
        await service.respond(meeting, action, reason, proposed_start)
    except AppError as error:
        await db.rollback()
        meeting = await service.linked(token)
        meeting._response_path = token
        return await response_page(db, meeting, error.message, error.status_code)
    meeting._response_path = token
    return await response_page(db, meeting)


@router.get("/{token}/calendar.ics", include_in_schema=False)
async def guest_calendar(token: str, proposed: bool = False, db: AsyncSession = Depends(get_db)):
    meeting = await MeetingService(db).linked(token)
    activity, organizer = await db.get(Activity, meeting.activity_id), await db.get(User, meeting.organizer_id)
    return Response(meeting_ics(meeting, activity, organizer, cancel=meeting.status in ("cancelled", "declined"), proposed=proposed and meeting.proposed_start is not None),
                    media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="meeting.ics"', "Cache-Control": "no-store"})
