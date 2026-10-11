"""Book a session with YGT's team. The free slots come from the hours set
in the admin site, minus anything already booked. A booking emails a
calendar invite to YGT's calendar and to the person who booked, so it
lands in both calendars (Google, Outlook and Apple all accept them)."""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.tenancy import ALL_TENANTS
from app.models.company_settings import CompanySettings
from app.models.platform import PlatformSetting, SessionBooking
from app.models.user import User
from app.schemas.platform import Availability, SlotDay, SlotsOut
from app.services import platform_email

TOPICS = {"onboarding": "Onboarding", "training": "Training", "support": "Help with a problem", "billing": "Billing", "other": "Other"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def free_slots(rules: Availability, taken: set[datetime], now: datetime) -> list[SlotDay]:
    """Every bookable start time in the coming days, in UTC."""
    zone = ZoneInfo(rules.timezone)
    start_t = time.fromisoformat(rules.start)
    end_t = time.fromisoformat(rules.end)
    step = timedelta(minutes=rules.slot_minutes)
    earliest = now + timedelta(hours=rules.min_notice_hours)
    today = now.astimezone(zone).date()
    days: list[SlotDay] = []
    for offset in range(rules.days_ahead + 1):
        day = today + timedelta(days=offset)
        if day.weekday() not in rules.weekdays or day in rules.blocked_dates:
            continue
        slot = datetime.combine(day, start_t, tzinfo=zone)
        last = datetime.combine(day, end_t, tzinfo=zone)
        slots = []
        while slot + step <= last:
            utc = slot.astimezone(timezone.utc)
            if utc >= earliest and utc not in taken:
                slots.append(utc)
            slot += step
        if slots:
            days.append(SlotDay(date=day, slots=slots))
    return days


class BookingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def availability(self) -> Availability:
        row = await self.db.get(PlatformSetting, "booking")
        return Availability.model_validate(row.value if row else {})

    async def save_availability(self, rules: Availability) -> Availability:
        row = await self.db.get(PlatformSetting, "booking")
        data = rules.model_dump(mode="json")
        if row is None:
            self.db.add(PlatformSetting(key="booking", value=data))
        else:
            row.value = data
        await self.db.flush()
        return rules

    async def _taken(self) -> set[datetime]:
        # Every company's bookings: a slot taken by anyone is gone.
        rows = await self.db.scalars(
            select(SessionBooking.starts_at).where(SessionBooking.status == "booked", SessionBooking.starts_at >= _now()),
            execution_options={ALL_TENANTS: True},
        )
        return {r.astimezone(timezone.utc) for r in rows}

    async def slots(self) -> SlotsOut:
        rules = await self.availability()
        days = free_slots(rules, await self._taken(), _now()) if rules.enabled else []
        return SlotsOut(timezone=rules.timezone, slot_minutes=rules.slot_minutes, days=days)

    async def mine(self) -> list[SessionBooking]:
        return list(await self.db.scalars(select(SessionBooking).order_by(SessionBooking.starts_at.desc()).limit(50)))

    async def book(self, user: User, starts_at: datetime, topic: str, notes: str | None) -> SessionBooking:
        rules = await self.availability()
        if starts_at.tzinfo is None:
            raise AppError("Send the time with its time zone", "BOOKING_TIME_INVALID")
        starts_at = starts_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
        available = {s for d in free_slots(rules, await self._taken(), _now()) for s in d.slots} if rules.enabled else set()
        if starts_at not in available:
            raise ConflictError("That time is no longer available. Please pick another.", "SLOT_TAKEN")
        booking = SessionBooking(
            company_id=user.company_id,
            user_id=user.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=rules.slot_minutes),
            topic=topic,
            notes=(notes or "").strip() or None,
            attendee_email=user.email,
            attendee_name=user.full_name,
        )
        self.db.add(booking)
        try:
            await self.db.flush()
        except IntegrityError:
            # Someone else took it in the same moment (unique index on the slot).
            raise ConflictError("That time was just taken. Please pick another.", "SLOT_TAKEN")
        await self._send_invites(booking, rules, method="REQUEST")
        return booking

    async def cancel(self, booking_id: uuid.UUID, *, by_team: bool = False) -> SessionBooking:
        booking = await self.db.get(SessionBooking, booking_id) if by_team else await self.db.scalar(select(SessionBooking).where(SessionBooking.id == booking_id))
        if booking is None:
            raise NotFoundError("Booking not found", "BOOKING_NOT_FOUND")
        if booking.status != "booked":
            return booking
        booking.status = "cancelled"
        booking.cancelled_at = _now()
        booking.sequence += 1
        await self.db.flush()
        await self._send_invites(booking, await self.availability(), method="CANCEL", by_team=by_team)
        return booking

    async def _send_invites(self, booking: SessionBooking, rules: Availability, method: str, by_team: bool = False) -> None:
        team = settings.BOOKING_CALENDAR_EMAIL or settings.SUPPORT_EMAIL
        organizer = settings.SUPPORT_EMAIL or team
        if not organizer:
            return
        company = await self.db.get(CompanySettings, booking.company_id)
        company_name = company.company_name if company else ""
        topic = TOPICS.get(booking.topic, booking.topic)
        local = booking.starts_at.astimezone(ZoneInfo(rules.timezone))
        when = f"{local:%A %d %B %Y, %H:%M} ({rules.timezone})"
        summary = f"YGT session: {topic} with {company_name}"
        description = f"{topic} session with {booking.attendee_name} ({company_name}).\n" + (f"Notes: {booking.notes}\n" if booking.notes else "") + (
            f"Join: {rules.meeting_link}" if rules.meeting_link else ""
        )
        ics = platform_email.ics_invite(
            uid=f"booking-{booking.id}@ygt",
            start=booking.starts_at,
            end=booking.ends_at,
            summary=summary,
            description=description,
            organizer=organizer,
            attendees=[(booking.attendee_name, booking.attendee_email)] + ([("YGT", team)] if team else []),
            method=method,
            sequence=booking.sequence,
            location=rules.meeting_link,
        )
        cancelled = method == "CANCEL"
        details = [("When", when), ("Topic", topic), ("Company", company_name)] + ([("Join", rules.meeting_link)] if rules.meeting_link else [])
        emails = [
            platform_email.compose(
                to=booking.attendee_email,
                subject=f"{'Cancelled' if cancelled else 'Booked'}: {summary}",
                title="Your session is cancelled" if cancelled else "Your session is booked",
                paragraphs=[f"Hi {booking.attendee_name.split(' ')[0]},"]
                + (["This session has been cancelled" + (" by YGT's team." if by_team else ".") + " You can book another time in the app."] if cancelled else ["Your session with YGT's team is booked. The invite is attached: add it to your calendar."]),
                details=details,
                button=("Book another time" if cancelled else "See your bookings", platform_email.app_link("/support?tab=sessions")),
                calendar=ics,
                calendar_method=method,
            )
        ]
        if team:
            emails.append(
                platform_email.compose(
                    to=team,
                    subject=f"{'Cancelled' if cancelled else 'New booking'}: {topic} with {company_name}, {local:%a %d %b %H:%M}",
                    title=f"{'Cancelled' if cancelled else 'New'} session: {booking.attendee_name}, {company_name}",
                    paragraphs=[],
                    details=details + [("Email", booking.attendee_email)],
                    quote=booking.notes,
                    button=("Open bookings", platform_email.app_link("/admin/bookings")),
                    reply_to=booking.attendee_email,
                    calendar=ics,
                    calendar_method=method,
                )
            )
        await platform_email.queue(self.db, *emails)
