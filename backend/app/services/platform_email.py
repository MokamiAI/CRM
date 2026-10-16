"""Emails YGT itself sends (not a company): password resets, help desk
updates, Contact us notifications and session booking invites. They use
the server's SMTP_* settings, from SMTP_FROM_EMAIL (e.g. billing@), with
no Reply-To. From a no-reply address, the footer names the public support
address instead."""
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.email_dispatch import commit_and_enqueue
from app.core.config import settings
from app.services.email_service import OutgoingEmail, render_email
from app.services.email_settings import EffectiveEmailConfig


def platform_config() -> EffectiveEmailConfig:
    return EffectiveEmailConfig(
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        use_tls=settings.SMTP_USE_TLS,
        # The no-reply sender, on the mail account's own domain (providers
        # such as GoDaddy refuse any other). No Reply-To: replies aren't read.
        from_email=settings.SMTP_FROM_EMAIL or settings.SUPPORT_EMAIL or "",
        from_name="YGT",
    )


def public_support_email() -> str | None:
    """The support address people may see (never the private inbox,
    unless no public one is set)."""
    return settings.PUBLIC_SUPPORT_EMAIL or settings.SUPPORT_EMAIL


def compose(
    to: str,
    subject: str,
    title: str,
    paragraphs: list[str],
    *,
    details: list[tuple[str, str]] | None = None,
    quote: str | None = None,
    button: tuple[str, str] | None = None,
    reply_to: str | None = None,
    calendar: str | None = None,
    calendar_method: str = "REQUEST",
) -> OutgoingEmail:
    email = render_email(
        "platform_message",
        to=to,
        subject=subject,
        title=title,
        paragraphs=paragraphs,
        details=details or [],
        quote=quote,
        button_label=button[0] if button else None,
        button_url=button[1] if button else None,
        # People can't reply to YGT's own emails; say where help is.
        # (Emails to the YGT team carry a Reply-To and need no such line.)
        footer=None if reply_to else _no_reply_footer(),
    )
    headers = {"Reply-To": reply_to} if reply_to else {}
    return OutgoingEmail(to=email.to, subject=email.subject, html=email.html, text=email.text, headers=headers, calendar=calendar, calendar_method=calendar_method)


def _no_reply_footer() -> str | None:
    """Only when sending from a no-reply address: from a real mailbox
    (e.g. billing@), people can simply reply."""
    sender = (settings.SMTP_FROM_EMAIL or "").lower()
    if not sender.startswith(("no-reply@", "noreply@", "donotreply@", "do-not-reply@")):
        return None
    support = public_support_email()
    line = "This is an automated email from YGT. Replies to it aren't received."
    return f"{line} Need help? Write to {support}." if support else line


async def queue(db: AsyncSession, *emails: OutgoingEmail) -> None:
    """Commits, then hands the emails to the worker (sending never blocks
    or fails the request)."""
    from app.tasks.platform_tasks import send_platform_email_task

    await db.commit()
    for email in emails:
        if email.to:
            await commit_and_enqueue(db, send_platform_email_task, asdict(email))


def app_link(path: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


# ---------------------------------------------------------------- calendar invites


def _ics_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """iCalendar lines are at most 75 octets; longer ones continue with a space."""
    out, chunk = [], ""
    for ch in line:
        if len((chunk + ch).encode()) > 73:
            out.append(chunk)
            chunk = " " + ch
        else:
            chunk += ch
    out.append(chunk)
    return "\r\n".join(out)


def ics_invite(
    uid: str,
    start: datetime,
    end: datetime,
    summary: str,
    description: str,
    organizer: str,
    attendees: list[tuple[str, str]],
    *,
    method: str = "REQUEST",
    sequence: int = 0,
    location: str | None = None,
) -> str:
    """A calendar invite (RFC 5545). REQUEST books it into each attendee's
    calendar; CANCEL with the same uid and a higher sequence removes it."""
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//YGT//Sessions//EN",
        "VERSION:2.0",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{_ics_time(datetime.now(timezone.utc))}",
        f"DTSTART:{_ics_time(start)}",
        f"DTEND:{_ics_time(end)}",
        f"SUMMARY:{_ics_text(summary)}",
        f"DESCRIPTION:{_ics_text(description)}",
        f"ORGANIZER;CN=YGT:mailto:{organizer}",
    ]
    if location:
        lines.append(f"LOCATION:{_ics_text(location)}")
    for name, email in attendees:
        lines.append(f"ATTENDEE;CN={_ics_text(name)};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}")
    lines += [f"STATUS:{'CANCELLED' if method == 'CANCEL' else 'CONFIRMED'}", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
