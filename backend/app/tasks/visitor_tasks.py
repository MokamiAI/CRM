# The nightly website report: at 22:00, the day's visitors emailed to YGT's
# team (SUPPORT_EMAIL, else the platform admins). Also drops visits older
# than site_visits.KEEP_DAYS.
from datetime import date, timedelta

from celery_app import celery_app

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.services import platform_email, site_visits
from app.tasks._runner import run_async


def _change(today: int, before: int) -> str:
    if before == 0:
        return "up from none yesterday"
    diff = today - before
    if diff == 0:
        return "the same as yesterday"
    return f"{abs(diff)} {'more' if diff > 0 else 'fewer'} than yesterday ({before})"


def _top(rows: list[dict], key: str, name: str, n: int = 5) -> str:
    return " · ".join(f"{r[name]} {r[key]}" for r in rows[:n]) or "—"


def compose_report(day: date, today: dict, yesterday: dict, week: dict, to: str):
    weekday = f"{day:%A} {day.day} {day:%B}"
    people = today["visitors"]
    phones = next((d["visitors"] for d in today["devices"] if d["device"] == "phone"), 0)
    lead = (f"{people} {'person' if people == 1 else 'people'} visited the website today, {_change(people, yesterday['visitors'])}."
            if people else "No one visited the website today.")
    return platform_email.compose(
        to=to,
        subject=f"Website: {people} visitor{'' if people == 1 else 's'} on {weekday}",
        title=f"Website visitors on {weekday}",
        paragraphs=[lead, f"In the last 7 days: {week['visitors']} visitors and {week['signups']} new sign-up{'' if week['signups'] == 1 else 's'}."],
        details=[
            ("Visitors", str(people)),
            ("Page views", str(today["page_views"])),
            ("Started the check-up", str(today["checkups_started"])),
            ("Finished the check-up", str(today["checkups_finished"])),
            ("New sign-ups", str(today["signups"])),
            ("On a phone", f"{phones} of {people}" if people else "—"),
            ("Top pages", _top(today["pages"], "views", "name")),
            ("Where they came from", _top(today["sources"], "visitors", "source")),
        ],
        button=("Open the full report", platform_email.app_link("/admin/visitors")),
    )


async def send_daily_report(day: date | None = None) -> int:
    day = day or site_visits.sa_today()
    recipients = [settings.SUPPORT_EMAIL] if settings.SUPPORT_EMAIL else sorted(settings.platform_admins)
    async with AsyncSessionLocal() as db:
        set_system(db)
        today = await site_visits.report(db, day, day)
        yesterday = await site_visits.report(db, day - timedelta(days=1), day - timedelta(days=1))
        week = await site_visits.report(db, day - timedelta(days=6), day)
        await site_visits.prune(db)
        emails = [compose_report(day, today, yesterday, week, to) for to in recipients]
        await platform_email.queue(db, *emails)  # commits
    return len(emails)


@celery_app.task(name="app.tasks.visitor_tasks.daily_visitor_report_task")
def daily_visitor_report_task():
    return run_async(send_daily_report)
