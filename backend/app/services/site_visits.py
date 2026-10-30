"""Visits to YGT's public website, counted without cookies.

The browser reports each public page it shows (and the check-up's start
and finish); nothing is stored on the visitor's device. A visitor is told
apart from others by a hash of their address and browser, salted with the
day, so the same person counts once a day and can't be followed across
days. The address itself is never stored. Signed-in people aren't counted
(the browser doesn't report them), nor are bots and link previews."""
import hashlib
import hmac
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.company_settings import CompanySettings
from app.models.platform import SiteVisit

TZ = ZoneInfo("Africa/Johannesburg")

PAGES = {
    "/": "Home",
    "/assessment": "Check-up",
    "/about": "About",
    "/contact": "Contact us",
    "/register": "Sign-up page",
    "/login": "Sign-in page",
    "/terms": "Terms",
    "/privacy": "Privacy policy",
    "/refunds": "Refund policy",
    "/delete-account": "Delete account",
}
EVENTS = {"view", "checkup_start", "checkup_done"}
KEEP_DAYS = 400

_BOT = re.compile(r"bot|crawl|spider|slurp|preview|headless|lighthouse|facebookexternalhit|curl|wget|python|httpclient", re.I)
# ?src= tags we put on our own links (QR codes, posts, emails).
_TAGS = {"qr": "QR code", "facebook": "Facebook", "fb": "Facebook", "instagram": "Instagram", "ig": "Instagram",
         "linkedin": "LinkedIn", "whatsapp": "WhatsApp", "wa": "WhatsApp", "email": "Email", "tiktok": "TikTok", "x": "X"}
# Sites that send visitors, by the end of their address.
_SITES = [
    ("google.", "Google"), ("bing.com", "Bing"), ("duckduckgo.com", "DuckDuckGo"), ("yahoo.", "Yahoo"),
    ("facebook.com", "Facebook"), ("fb.com", "Facebook"), ("instagram.com", "Instagram"), ("linkedin.com", "LinkedIn"),
    ("lnkd.in", "LinkedIn"), ("whatsapp.com", "WhatsApp"), ("wa.me", "WhatsApp"), ("t.co", "X"), ("x.com", "X"),
    ("twitter.com", "X"), ("tiktok.com", "TikTok"), ("youtube.com", "YouTube"), ("chatgpt.com", "ChatGPT"),
]


def sa_today() -> date:
    return datetime.now(TZ).date()


def page_name(path: str) -> str:
    return PAGES.get(path, path)


def source_of(src: str | None, referrer: str | None) -> str:
    """Our own ?src= tag first, then the site the visitor came from."""
    tag = re.sub(r"[^a-z0-9_-]", "", (src or "").lower())[:30]
    if tag:
        return _TAGS.get(tag, tag.replace("_", " ").replace("-", " ").title())
    host = (urlparse(referrer or "").hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("l.")
    own = (urlparse(settings.FRONTEND_URL).hostname or "").lower().removeprefix("www.")
    if not host or host == own or host.endswith("." + own):
        return "Direct"
    for end, name in _SITES:
        if host == end or host.endswith("." + end) or (end.endswith(".") and (host.startswith(end) or f".{end}" in host)):
            return name
    return host[:40]


def device_of(user_agent: str) -> str:
    if re.search(r"ipad|tablet", user_agent, re.I):
        return "tablet"
    if re.search(r"mobi|android|iphone", user_agent, re.I):
        return "phone"
    return "computer"


def _visitor(day: date, ip: str, user_agent: str) -> str:
    message = f"{day.isoformat()}|{ip}|{user_agent}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), message, hashlib.sha256).hexdigest()[:16]


async def record(db: AsyncSession, *, event: str, path: str, referrer: str | None, src: str | None, user_agent: str, ip: str) -> bool:
    """Stores one visit; False (and nothing stored) for bots and unknown pages."""
    path = (path or "").split("?")[0].split("#")[0].rstrip("/") or "/"
    if event not in EVENTS or path not in PAGES or not user_agent or _BOT.search(user_agent):
        return False
    day = sa_today()
    db.add(SiteVisit(day=day, event=event, path=path, source=source_of(src, referrer),
                     device=device_of(user_agent), visitor=_visitor(day, ip, user_agent[:400])))
    return True


async def report(db: AsyncSession, start: date, end: date) -> dict:
    """Visitors from start to end (inclusive). The visitor hash already
    changes each day, so counting distinct hashes sums each day's visitors."""
    within = (SiteVisit.day >= start, SiteVisit.day <= end)
    people = func.count(func.distinct(SiteVisit.visitor))

    async def visitors(*where) -> int:
        return await db.scalar(select(people).where(*within, *where)) or 0

    by_day = {d: (v, p) for d, v, p in await db.execute(
        select(SiteVisit.day, people, func.count().filter(SiteVisit.event == "view")).where(*within).group_by(SiteVisit.day))}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    async def grouped(column, limit: int, *where):
        rows = await db.execute(select(column, people).where(*within, *where).group_by(column).order_by(people.desc(), column).limit(limit))
        return list(rows)

    pages = await db.execute(
        select(SiteVisit.path, func.count(), people).where(*within, SiteVisit.event == "view")
        .group_by(SiteVisit.path).order_by(func.count().desc()).limit(10))
    signups = await db.scalar(select(func.count()).select_from(CompanySettings).where(
        CompanySettings.created_at >= datetime.combine(start, time(), TZ),
        CompanySettings.created_at < datetime.combine(end + timedelta(days=1), time(), TZ))) or 0
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "visitors": await visitors(),
        "page_views": sum(p for _, p in by_day.values()),
        "checkups_started": await visitors(SiteVisit.event == "checkup_start"),
        "checkups_finished": await visitors(SiteVisit.event == "checkup_done"),
        "signups": signups,
        "by_day": [{"day": d.isoformat(), "visitors": by_day.get(d, (0, 0))[0], "page_views": by_day.get(d, (0, 0))[1]} for d in days],
        "pages": [{"path": p, "name": page_name(p), "views": n, "visitors": v} for p, n, v in pages],
        "sources": [{"source": s, "visitors": v} for s, v in await grouped(SiteVisit.source, 10)],
        "devices": [{"device": d, "visitors": v} for d, v in await grouped(SiteVisit.device, 3)],
    }


async def prune(db: AsyncSession) -> None:
    await db.execute(delete(SiteVisit).where(SiteVisit.day < sa_today() - timedelta(days=KEEP_DAYS)))
