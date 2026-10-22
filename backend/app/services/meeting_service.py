"""Email-based meeting scheduling. YGT is authoritative; .ics is portable.

Guest responses use signed, revision-specific links. Reading a link never
changes a booking. Competing requests lock the same calendar identities.
"""
import hashlib
import uuid
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import jwt
from sqlalchemy import func, or_, select

from app.api.email_dispatch import commit_and_enqueue_each
from app.core.config import settings
from app.core.activity_access import CHECK_AVAILABILITY
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token
from app.core.tenancy import current_company_id, set_tenant
from app.models.crm import Activity, Contact, Deal, TaskUpdate
from app.models.enums import ActivityType, UserRole
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.meeting import CalendarBlock, MeetingContactOut
from app.services.email_service import EmailNotConfiguredError
from app.services.email_settings import resolve_email_config
from app.services.platform_email import _fold, _ics_text, _ics_time, compose

BUSY = {"invited", "accepted", "proposed"}


def _utc(value, zone):
    if value.tzinfo is None:
        local = value.replace(tzinfo=ZoneInfo(zone))
        if local.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None) != value:
            raise ConflictError("That local time does not exist. Choose another time", "MEETING_TIME_INVALID")
        value = local
    return value.astimezone(timezone.utc)


def response_url(meeting):
    token = jwt.encode({"type": "meeting-response", "sub": str(meeting.id), "company": str(meeting.company_id),
                        "version": meeting.sequence, "email": meeting.attendee_email.lower(),
                        "exp": max(datetime.now(timezone.utc), meeting.ends_at) + timedelta(days=90)},
                       settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/meetings/{token}"


def meeting_ics(meeting, activity, organizer, *, cancel=False, proposed=False):
    def text(value):
        return _ics_text((value or "").replace("\r\n", "\n").replace("\r", "\n"))
    def param(value):
        return '"' + value.replace("^", "^^").replace('"', "^'").replace("\r", "").replace("\n", "^n") + '"'
    start, end = (meeting.proposed_start, meeting.proposed_end) if proposed else (meeting.starts_at, meeting.ends_at)
    status = "CANCELLED" if cancel else "TENTATIVE" if proposed or meeting.status != "accepted" else "CONFIRMED"
    uid = f"ygt-meeting-{meeting.id}" + (f"-proposal-{meeting.sequence}" if proposed else "") + "@yougt.co.za"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//YGT//Meetings//EN", f"METHOD:{'CANCEL' if cancel else 'REQUEST'}",
             "BEGIN:VEVENT", f"UID:{uid}", f"SEQUENCE:{meeting.sequence * 10 + (2 if cancel else 1 if status == 'CONFIRMED' else 0)}",
             f"DTSTAMP:{_ics_time(datetime.now(timezone.utc))}", f"DTSTART:{_ics_time(start)}", f"DTEND:{_ics_time(end)}",
             f"SUMMARY:{text(('Proposed time: ' if proposed else '') + activity.subject)}", f"STATUS:{status}", "TRANSP:OPAQUE",
             f"ORGANIZER;CN={param(organizer.full_name)}:mailto:{organizer.email}",
             f"ATTENDEE;CN={param(meeting.attendee_name)};ROLE=REQ-PARTICIPANT;PARTSTAT={'ACCEPTED' if meeting.status == 'accepted' else 'NEEDS-ACTION'};RSVP=FALSE:mailto:{meeting.attendee_email}",
             f"DESCRIPTION:{text((activity.note or '') + chr(10) + 'Respond in YGT: ' + response_url(meeting))}",
             f"URL:{response_url(meeting)}"]
    if meeting.location:
        lines.append(f"LOCATION:{text(meeting.location)}")
    return "\r\n".join(_fold(line) for line in lines + ["END:VEVENT", "END:VCALENDAR"]) + "\r\n"


class MeetingService:
    def __init__(self, db):
        self.db = db

    async def contact(self, *, deal_id=None, customer_id=None, contact_id=None):
        if deal_id:
            deal = await self.db.get(Deal, deal_id)
            if deal is None:
                raise NotFoundError("Pipeline workspace not found", "DEAL_NOT_FOUND")
            customer_id, contact_id = deal.customer_id, deal.contact_id or contact_id
        person = None
        if contact_id:
            person = await self.db.get(Contact, contact_id)
            if person is None or (customer_id and person.customer_id != customer_id):
                raise NotFoundError("Contact person not found", "CONTACT_NOT_FOUND")
        elif customer_id:
            person = await self.db.scalar(select(Contact).where(Contact.customer_id == customer_id).order_by(Contact.is_primary.desc(), Contact.created_at, Contact.id).limit(1))
        return MeetingContactOut(contact_id=person.id, name=" ".join(filter(None, [person.first_name, person.last_name])), email=person.email or "") if person else MeetingContactOut()

    async def attach(self, activities):
        if not activities:
            return activities
        meetings = (await self.db.scalars(select(Meeting).where(Meeting.activity_id.in_([a.id for a in activities])))).all()
        indexed = {meeting.activity_id: meeting for meeting in meetings}
        for activity in activities:
            activity.meeting = indexed.get(activity.id)
        return activities

    async def get(self, activity_id, *, lock=False):
        if lock:
            await self.db.scalar(select(Activity).where(Activity.id == activity_id).with_for_update())
        query = select(Meeting).where(Meeting.activity_id == activity_id)
        meeting = await self.db.scalar(query.with_for_update() if lock else query)
        if meeting is None:
            raise NotFoundError("Meeting invitation not found", "MEETING_NOT_FOUND")
        return meeting

    async def company(self):
        return await CompanySettingsRepository(self.db).get_current()

    async def _locks(self, activity, attendee_email, organizer_id):
        identities = {f"user:{organizer_id}", f"email:{attendee_email.lower()}"}
        identities |= {f"user:{person}" for person in [activity.owner_id, *(activity.assignee_ids or [])] if person}
        company_id = current_company_id(self.db)
        keys = sorted(int.from_bytes(hashlib.blake2b(f"{company_id}:{identity}".encode(), digest_size=8).digest(), "big", signed=True) for identity in identities)
        for key in keys:
            await self.db.execute(select(func.pg_advisory_xact_lock(key)))

    async def _available(self, activity, start, end, email, organizer_id):
        await self._locks(activity, email, organizer_id)
        people = {str(organizer_id), str(activity.owner_id), *(activity.assignee_ids or [])}
        rows = (await self.db.execute(select(Meeting, Activity).join(Activity, Activity.id == Meeting.activity_id)
                                     .where(Meeting.status.in_(BUSY), Meeting.activity_id != activity.id)
                                     .execution_options(**{CHECK_AVAILABILITY: True}))).all()
        for other, parent in rows:
            same_people = bool(people & {str(other.organizer_id), str(parent.owner_id), *(parent.assignee_ids or [])})
            if not same_people and other.attendee_email.lower() != email.lower():
                continue
            for beginning, ending in [(other.starts_at, other.ends_at), (other.proposed_start, other.proposed_end)]:
                if beginning and ending and start < ending and end > beginning:
                    raise ConflictError("That time is already held in the YGT calendar. Choose another time", "MEETING_TIME_BUSY")
        # Existing internal meetings also occupy their owners' calendars.
        zone = (await self.company()).default_timezone
        legacy = (await self.db.scalars(select(Activity).where(Activity.type == ActivityType.MEETING,
                  Activity.id != activity.id, Activity.done.is_(False), Activity.due_time.is_not(None),
                  ~Activity.id.in_(select(Meeting.activity_id))).execution_options(**{CHECK_AVAILABILITY: True}))).all()
        for parent in legacy:
            if not (people & {str(parent.owner_id), *(parent.assignee_ids or [])}):
                continue
            beginning = _utc(datetime.combine(parent.due_date, parent.due_time), zone)
            if start < beginning + timedelta(minutes=30) and end > beginning:
                raise ConflictError("That time overlaps an existing internal meeting", "MEETING_TIME_BUSY")

    async def _emails(self, meeting, activity, message, *, cancel=False, proposed=False):
        organizer = await self.db.get(User, meeting.organizer_id)
        company = await self.company()
        start = meeting.proposed_start if proposed else meeting.starts_at
        end = meeting.proposed_end if proposed else meeting.ends_at
        zone = ZoneInfo(meeting.timezone)
        details = [("When", f"{start.astimezone(zone):%d %b %Y %H:%M} - {end.astimezone(zone):%H:%M} ({meeting.timezone})"),
                   ("Organiser", organizer.full_name), ("Attendee", meeting.attendee_name)]
        if meeting.location:
            details.append(("Location / call link", meeting.location))
        calendar = meeting_ics(meeting, activity, organizer, cancel=cancel, proposed=proposed)
        signature = organizer.email_signature or company.email_signature
        guest = compose(to=meeting.attendee_email, subject=f"{message}: {activity.subject}", title=message,
                        paragraphs=[f"Hi {meeting.attendee_name},", f"{organizer.full_name} from {company.company_name}: {activity.subject}.",
                                    "Use Respond in YGT to record your choice. The attached calendar event can be added to your own calendar."],
                        details=details, quote=meeting.response_reason or activity.note,
                        button=("Respond in YGT", response_url(meeting)) if not cancel and meeting.status == "invited" else None,
                        calendar=calendar, calendar_method="CANCEL" if cancel else "REQUEST", reply_to=organizer.email,
                        from_name=company.company_name, signature=signature)
        hosts = []
        ids = {meeting.organizer_id, activity.owner_id, *(uuid.UUID(str(person)) for person in (activity.assignee_ids or []))} - {None}
        for person in (await self.db.scalars(select(User).where(User.id.in_(ids), User.is_active.is_(True)))).all():
            hosts.append(compose(to=person.email, subject=f"{message}: {activity.subject}", title=message,
                         paragraphs=[f"Meeting with {meeting.attendee_name} ({meeting.attendee_email})."], details=details,
                         quote=meeting.response_reason or activity.note,
                         button=("Open meeting", f"{settings.FRONTEND_URL.rstrip('/')}/activities?task={activity.id}"),
                         calendar=calendar, calendar_method="CANCEL" if cancel else "REQUEST", reply_to=meeting.attendee_email,
                         from_name=company.company_name))
        return [guest, *hosts]

    async def _queue(self, emails):
        from app.tasks.email_tasks import send_meeting_email_task
        company_id = str(current_company_id(self.db))
        await commit_and_enqueue_each(self.db, send_meeting_email_task, [(company_id, asdict(email)) for email in emails])

    def _history(self, meeting, activity, text, actor_id=None):
        self.db.add(TaskUpdate(activity_id=activity.id, author_id=actor_id, note=text))

    async def schedule(self, activity, draft, user):
        if activity.type != ActivityType.MEETING:
            raise ConflictError("Only meetings can send invitations", "MEETING_TYPE_REQUIRED")
        company = await self.company()
        config = resolve_email_config(company)
        if not config.host or not config.from_email:
            raise EmailNotConfiguredError()
        if not activity.due_time:
            raise ConflictError("Choose a meeting time before sending an invitation", "MEETING_TIME_REQUIRED")
        contact = await self.contact(deal_id=activity.deal_id, customer_id=activity.customer_id, contact_id=activity.contact_id)
        name = (contact.name or draft.attendee_name or "").strip()
        email = (contact.email or draft.attendee_email or "").strip()
        if not name or not email:
            raise ConflictError("The contact person's name and email are required for a meeting invitation", "MEETING_CONTACT_REQUIRED")
        # A supplied missing email is saved back to the selected contact.
        if contact.contact_id and not contact.email:
            (await self.db.get(Contact, contact.contact_id)).email = email
        if not contact.contact_id and activity.customer_id:
            from app.services.contact_service import ContactService
            from app.schemas.crm import ContactCreate
            first, _, last = name.partition(" ")
            person = await ContactService(self.db).create_contact(activity.customer_id, ContactCreate(first_name=first[:120], last_name=last[:120] or None, email=email))
            contact.contact_id = person.id
            if activity.deal_id:
                deal = await self.db.get(Deal, activity.deal_id)
                if not deal.contact_id:
                    deal.contact_id = person.id
        if contact.contact_id:
            activity.contact_id = contact.contact_id
        start = _utc(datetime.combine(activity.due_date, activity.due_time), company.default_timezone)
        if start <= datetime.now(timezone.utc):
            raise ConflictError("Choose a future meeting time", "MEETING_TIME_PAST")
        end = start + timedelta(minutes=draft.duration_minutes)
        existing = await self.db.scalar(select(Meeting).where(Meeting.activity_id == activity.id).with_for_update())
        organizer_id = existing.organizer_id if existing else (activity.owner_id or user.id)
        await self._available(activity, start, end, email, organizer_id)
        emails = []
        if existing and existing.proposed_start:
            emails += await self._emails(existing, activity, "Proposed time released", cancel=True, proposed=True)
        if existing and existing.attendee_email.lower() != email.lower():
            emails += await self._emails(existing, activity, "Previous invitation cancelled", cancel=True)
        meeting = existing or Meeting(activity_id=activity.id, organizer_id=organizer_id, company_id=activity.company_id)
        meeting.attendee_name, meeting.attendee_email = name, email
        meeting.starts_at, meeting.ends_at, meeting.timezone = start, end, company.default_timezone
        meeting.location, meeting.status = (draft.location or "").strip() or None, "invited"
        meeting.sequence = (existing.sequence + 1) if existing else 0
        meeting.response_reason = meeting.responded_at = meeting.proposed_start = meeting.proposed_end = None
        if not existing:
            self.db.add(meeting)
        await self.db.flush()
        activity.meeting = meeting
        self._history(meeting, activity, f"Meeting invitation {'updated' if existing else 'sent'} to {email}", user.id)
        emails += await self._emails(meeting, activity, "Meeting invitation")
        await self._queue(emails)
        return meeting

    async def linked(self, token, *, lock=False):
        try:
            payload = decode_token(token)
            if payload.get("type") != "meeting-response":
                raise ValueError()
            company_id, meeting_id = uuid.UUID(payload["company"]), uuid.UUID(payload["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise UnauthorizedError("This meeting link is invalid or expired")
        set_tenant(self.db, company_id)
        query = select(Meeting).where(Meeting.id == meeting_id)
        meeting = await self.db.scalar(query)
        if meeting is not None and lock:
            await self.db.scalar(select(Activity).where(Activity.id == meeting.activity_id).with_for_update())
            meeting = await self.db.scalar(query.with_for_update().execution_options(populate_existing=True))
        if meeting is None or meeting.sequence != payload.get("version") or meeting.attendee_email.lower() != payload.get("email"):
            raise UnauthorizedError("This meeting invitation has changed. Use the latest email")
        return meeting

    async def respond(self, meeting, action, reason="", proposed_start=None):
        activity = await self.db.get(Activity, meeting.activity_id)
        wanted = {"accept": "accepted", "decline": "declined", "propose": "proposed"}[action]
        if meeting.status == wanted:
            return meeting
        if meeting.status != "invited":
            raise ConflictError("A response is already recorded. Contact the organiser to change it", "MEETING_ALREADY_RESPONDED")
        reason = reason.strip()
        if action == "decline" and not reason:
            raise ConflictError("Please give a reason for declining", "MEETING_REASON_REQUIRED")
        if meeting.ends_at <= datetime.now(timezone.utc):
            raise ConflictError("This meeting has already ended. Contact the organiser", "MEETING_ENDED")
        if action == "propose":
            if not proposed_start:
                raise ConflictError("Choose a proposed date and time", "MEETING_PROPOSAL_REQUIRED")
            start = _utc(proposed_start, meeting.timezone)
            if start <= datetime.now(timezone.utc):
                raise ConflictError("Propose a future date and time", "MEETING_TIME_PAST")
            end = start + (meeting.ends_at - meeting.starts_at)
            await self._available(activity, start, end, meeting.attendee_email, meeting.organizer_id)
            meeting.proposed_start, meeting.proposed_end = start, end
        meeting.status, meeting.response_reason, meeting.responded_at = wanted, reason or None, datetime.now(timezone.utc)
        self._history(meeting, activity, f"{meeting.attendee_name}: meeting {wanted}." + (f" {reason}" if reason else ""))
        await self.db.flush()
        await self._queue(await self._emails(meeting, activity, f"Meeting {wanted}", cancel=action == "decline", proposed=action == "propose"))
        return meeting

    async def review(self, activity_id, accept, reason, user):
        meeting = await self.get(activity_id, lock=True)
        if user.id != meeting.organizer_id and user.role not in (UserRole.ADMIN, UserRole.MANAGER):
            raise PermissionDeniedError("Only the organiser or a manager can decide a proposed time")
        if meeting.status != "proposed" or not meeting.proposed_start:
            raise ConflictError("There is no proposed time to review", "MEETING_NO_PROPOSAL")
        activity = await self.db.get(Activity, activity_id)
        emails = await self._emails(meeting, activity, "Proposed time released", cancel=True, proposed=True)
        if accept:
            await self._available(activity, meeting.proposed_start, meeting.proposed_end, meeting.attendee_email, meeting.organizer_id)
            meeting.starts_at, meeting.ends_at, meeting.status = meeting.proposed_start, meeting.proposed_end, "accepted"
            local = meeting.starts_at.astimezone(ZoneInfo(meeting.timezone))
            activity.due_date, activity.due_time = local.date(), local.time().replace(tzinfo=None)
        else:
            meeting.status = "invited"
        meeting.sequence += 1
        meeting.proposed_start = meeting.proposed_end = None
        meeting.response_reason = (reason or "").strip() or None
        self._history(meeting, activity, "Proposed meeting time " + ("approved" if accept else "not approved") + (f": {reason}" if reason else ""), user.id)
        await self.db.flush()
        emails += await self._emails(meeting, activity, "New meeting time confirmed" if accept else "Original meeting time offered again")
        await self._queue(emails)
        return meeting

    async def cancel(self, activity_id, user):
        meeting = await self.get(activity_id, lock=True)
        if user.id != meeting.organizer_id and user.role not in (UserRole.ADMIN, UserRole.MANAGER):
            raise PermissionDeniedError("Only the organiser or a manager can cancel this meeting")
        if meeting.status == "cancelled":
            return meeting
        activity = await self.db.get(Activity, activity_id)
        emails = await self._emails(meeting, activity, "Proposed time released", cancel=True, proposed=True) if meeting.proposed_start else []
        meeting.status, meeting.sequence = "cancelled", meeting.sequence + 1
        meeting.proposed_start = meeting.proposed_end = None
        self._history(meeting, activity, "Meeting cancelled", user.id)
        await self.db.flush()
        emails += await self._emails(meeting, activity, "Meeting cancelled", cancel=True)
        await self._queue(emails)
        return meeting

    async def calendar(self, start, end, user, mine=True):
        if not mine and user.role not in (UserRole.ADMIN, UserRole.MANAGER):
            raise PermissionDeniedError("Only admins and managers can view everyone's calendar")
        if end <= start or (end - start).days > 93:
            raise ConflictError("Choose a calendar range of up to 93 days", "CALENDAR_RANGE_INVALID")
        company = await self.company()
        zone = company.default_timezone
        first, last = _utc(datetime.combine(start, time.min), zone), _utc(datetime.combine(end, time.min), zone)
        records = []
        rows = (await self.db.execute(select(Meeting, Activity).join(Activity, Activity.id == Meeting.activity_id).where(Meeting.status.in_(BUSY)))).all()
        for meeting, activity in rows:
            participants = {meeting.organizer_id, activity.owner_id, *(uuid.UUID(str(person)) for person in activity.assignee_ids or [])}
            if mine and user.id not in participants:
                continue
            for beginning, ending, proposed in [(meeting.starts_at, meeting.ends_at, False), (meeting.proposed_start, meeting.proposed_end, True)]:
                if beginning and ending and beginning < last and ending > first:
                    records.append(CalendarBlock(activity_id=activity.id, subject=activity.subject, starts_at=beginning, ends_at=ending,
                                                  status="proposed" if proposed else meeting.status, proposed=proposed, attendee_name=meeting.attendee_name))
        legacy = (await self.db.scalars(select(Activity).where(Activity.type == ActivityType.MEETING, Activity.done.is_(False),
                  Activity.due_time.is_not(None), ~Activity.id.in_(select(Meeting.activity_id))))).all()
        for activity in legacy:
            if mine and user.id not in {activity.owner_id, *(uuid.UUID(str(person)) for person in activity.assignee_ids or [])}:
                continue
            beginning = _utc(datetime.combine(activity.due_date, activity.due_time), zone)
            if first <= beginning < last:
                records.append(CalendarBlock(activity_id=activity.id, subject=activity.subject, starts_at=beginning,
                                              ends_at=beginning + timedelta(minutes=30), status="internal"))
        return sorted(records, key=lambda event: event.starts_at)
