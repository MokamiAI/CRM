# Every minute (celery_app.conf.beat_schedule "due-reminders"): remind each
# person of their activities as they fall due, and once a week of open
# deals with no next step. Each reminder has a key, so it's sent once.
import logging
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.crm import Activity, Deal
from app.models.enums import ActivityType, DealStage
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.notify import notify, send_push
from app.services.activity_service import ActivityService
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)

# Calls and meetings get their existing one-minute notice. Timed tasks
# get two hours; unfinished tasks also receive one daily digest per person.
LEAD_TIME = timedelta(minutes=1)
# An activity without a time is due "today": remind at this hour.
ALL_DAY_AT = time(8, 0)
# Don't wake people about things long past (e.g. after the server was off).
STALE_AFTER = timedelta(hours=2)


def _when(activity: Activity, tz: ZoneInfo) -> datetime:
    return datetime.combine(activity.due_date, activity.due_time or ALL_DAY_AT, tz)


def _activity_text(activity: Activity, tz: ZoneInfo) -> tuple[str, str]:
    at = activity.due_time.strftime("%H:%M") if activity.due_time else None
    title = f"Due {'at ' + at if at else 'today'}: {activity.subject}"
    body = f"{activity.subject} is due {'at ' + at if at else 'today'}" + (f". {activity.note}" if activity.note else ".")
    return title, body


async def remind_company(company_id: uuid.UUID, now: datetime | None = None) -> int:
    """One company's due reminders. Returns how many were sent."""
    sent = 0
    async with AsyncSessionLocal() as db:
        set_tenant(db, company_id)
        company = await CompanySettingsRepository(db).get_current()
        try:
            tz = ZoneInfo(company.default_timezone)
        except Exception:
            tz = ZoneInfo("Africa/Johannesburg")
        now = (now or datetime.now(tz)).astimezone(tz)
        today = now.date()
        # One daily digest per person, in the company's local time. Freshly
        # created tasks don't immediately trigger a redundant reminder.
        if time(9, 0) <= now.time().replace(tzinfo=None) < time(18, 0):
            tasks = (await db.scalars(select(Activity).where(
                Activity.type == ActivityType.TASK, Activity.done.is_(False), Activity.daily_reminders.is_(True)
            ))).all()
            grouped = {}
            morning = datetime.combine(today, time(9, 0), tz)
            for task in tasks:
                if task.created_at.astimezone(tz) >= morning:
                    continue
                for person_id in ActivityService.participants(task):
                    grouped.setdefault(person_id, []).append(task)
            for person_id, pending in grouped.items():
                person = await db.get(User, person_id)
                if person is None:
                    continue
                body = "\n".join(f"- {task.subject} (due {task.due_date.isoformat()}" +
                                 (f" {task.due_time:%H:%M}" if task.due_time else "") + ")" for task in pending[:20])
                if len(pending) > 20:
                    body += f"\nAnd {len(pending) - 20} more in Activities."
                note = await notify(db, person, kind="task_digest", title=f"Your daily tasks: {len(pending)} unfinished",
                                    body=body, link="/activities", params={"count": len(pending)},
                                    key=f"task-digest:{today.isoformat()}")
                sent += note is not None
        # Open activities due by tomorrow (so a 00:00 one is caught at 23:59).
        rows = await db.scalars(
            select(Activity).where(
                Activity.done.is_(False), Activity.owner_id.is_not(None), Activity.due_date <= today + timedelta(days=1)
            )
        )
        due_activities = list(rows.all())
        from app.services.meeting_service import MeetingService
        await MeetingService(db).attach(due_activities)
        for activity in due_activities:
            if getattr(activity, "meeting", None) and activity.meeting.status in ("declined", "cancelled"):
                continue
            # Date-only tasks are covered by the daily digest by default.
            # People who turn that off can retain the single due-date notice.
            if activity.type == ActivityType.TASK and activity.due_time is None and activity.daily_reminders:
                continue
            if activity.type == ActivityType.TASK and not activity.deadline_reminders:
                continue
            when = _when(activity, tz)
            if activity.due_time is None:
                # All day: any time on its day from 08:00. Made (or given)
                # during that day after 08:00: they already know, no ping.
                if not (activity.due_date == today and now >= when) or activity.created_at.astimezone(tz) >= when:
                    continue
            elif activity.type == ActivityType.TASK:
                if not (when - timedelta(hours=2) <= now < when):
                    continue
            elif not (when - LEAD_TIME <= now < when + STALE_AFTER):
                continue
            title, body = _activity_text(activity, tz)
            timed_task = activity.type == ActivityType.TASK and activity.due_time is not None
            if timed_task:
                title = f"Task deadline approaching: {activity.subject}"
                body = f"{activity.subject} is due at {activity.due_time:%H:%M} ({company.default_timezone}), within two hours."
            link = f"/activities?task={activity.id}"
            for person_id in ActivityService.participants(activity):
                owner = await db.get(User, person_id)
                if owner is None:
                    continue
                note = await notify(
                    db, owner,
                    kind="task_deadline" if timed_task else "activity_due",
                    title=title,
                    body=body,
                    link=link,
                    params={"subject": activity.subject, "time": activity.due_time.strftime("%H:%M") if activity.due_time else None, "type": activity.type.value},
                    key=f"due:{activity.id}:{activity.due_date.isoformat()}:{activity.due_time or ''}",
                )
                sent += note is not None
        # Monday 08:00: open deals nobody has planned a next step for.
        if now.weekday() == 0 and now.time() >= ALL_DAY_AT:
            week = today.isocalendar()
            planned = exists().where(Activity.deal_id == Deal.id, Activity.done.is_(False))
            stale = await db.scalars(
                select(Deal).where(
                    Deal.stage.notin_([DealStage.WON, DealStage.LOST]), Deal.owner_id.is_not(None), ~planned
                )
            )
            for deal in stale.all():
                owner = await db.get(User, deal.owner_id)
                if owner is None:
                    continue
                note = await notify(
                    db, owner,
                    kind="deal_no_next_step",
                    title=f"No next step: {deal.title}",
                    body=f"{deal.title} has nothing planned. Schedule a call, meeting or task so it doesn't go cold.",
                    link=f"/deals/{deal.id}",
                    params={"deal": deal.title},
                    key=f"nonext:{deal.id}:{week.year}-W{week.week}",
                    email=False,  # a nudge in the app and on the phone is enough
                )
                sent += note is not None
        from app.services.mcem_service import McemService
        sent += await McemService(db).remind(today)
    return sent


async def remind_all(now: datetime | None = None) -> int:
    async with AsyncSessionLocal() as session:
        set_system(session)
        company_ids = await CompanySettingsRepository(session).list_ids()
    sent = 0
    for company_id in company_ids:
        # One company at a time: a problem in one doesn't stop the rest.
        try:
            sent += await remind_company(company_id, now)
        except Exception:
            logger.exception("Due reminders failed for company %s", company_id)
    return sent


@celery_app.task(name="app.tasks.notification_tasks.due_reminders_task")
def due_reminders_task() -> int:
    return run_async(remind_all)


@celery_app.task(
    name="app.tasks.notification_tasks.send_push_task",
    autoretry_for=(OSError,),
    retry_backoff=30,
    max_retries=3,
)
def send_push_task(notification_id: str) -> int:
    return run_async(lambda: send_push(uuid.UUID(notification_id)))
