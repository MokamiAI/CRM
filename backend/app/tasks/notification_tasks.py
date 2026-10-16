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
from app.models.enums import DealStage
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.notify import notify, send_push
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)

# Reminders go out this long before an activity's time.
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
        # Open activities due by tomorrow (so a 00:00 one is caught at 23:59).
        rows = await db.scalars(
            select(Activity).where(
                Activity.done.is_(False), Activity.owner_id.is_not(None), Activity.due_date <= today + timedelta(days=1)
            )
        )
        for activity in rows.all():
            when = _when(activity, tz)
            if activity.due_time is None:
                # All day: any time on its day from 08:00 (e.g. made at 14:00).
                if not (activity.due_date == today and now >= when):
                    continue
            elif not (when - LEAD_TIME <= now < when + STALE_AFTER):
                continue
            owner = await db.get(User, activity.owner_id)
            if owner is None:
                continue
            title, body = _activity_text(activity, tz)
            link = f"/deals/{activity.deal_id}" if activity.deal_id else f"/customers/{activity.customer_id}" if activity.customer_id else "/activities"
            note = await notify(
                db, owner,
                kind="activity_due",
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
