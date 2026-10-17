"""Shared, editable help desk wording. Substitution is plain text only."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformSetting

DEFAULT_TEMPLATES = [
    {"key": "acknowledged", "name": "Ticket received", "body": "Hi {name},\n\nThanks for getting in touch. We've received ticket #{number}: {subject}. Our support team will review it and email you with an update. You can follow your ticket or add more details in YGT.\n\nYGT Support"},
    {"key": "open", "name": "Reopened", "body": "Your ticket #{number} is open. We'll review the latest details and keep you updated.\n\nYGT Support"},
    {"key": "in_progress", "name": "Investigation started", "body": "Hi {name},\n\nWe're working on ticket #{number}: {subject}. We're investigating the issue and will share an update as soon as we have more information.\n\nYGT Support"},
    {"key": "waiting", "name": "Waiting on client", "body": "Hi {name},\n\nWe're waiting for your response on ticket #{number}: {subject}. Please reply in YGT with the requested information so we can continue working on your ticket.\n\nYGT Support"},
    {"key": "resolved", "name": "Issue resolved", "body": "Hi {name},\n\nWe've marked ticket #{number}: {subject} as resolved. Please check that everything is working. If you still need help, reply in YGT and your ticket will reopen.\n\nYGT Support"},
    {"key": "closed", "name": "Ticket closed", "body": "Hi {name},\n\nTicket #{number}: {subject} is now closed. Thank you for contacting us. Please open a new ticket in YGT if you need further help.\n\nYGT Support"},
    {"key": "progress_update", "name": "Still working on it", "body": "Hi {name},\n\nA quick update on ticket #{number}: we're still working on this. We don't have a resolution yet, but will let you know when there is progress. Thank you for your patience.\n\nYGT Support"},
]


async def templates(db: AsyncSession) -> list[dict]:
    row = await db.get(PlatformSetting, "ticket_templates")
    overrides = {t["key"]: t for t in row.value.get("templates", [])} if row else {}
    return [overrides.get(t["key"], t) for t in DEFAULT_TEMPLATES]


def render(body: str, ticket, name: str) -> str:
    # One pass: inserted names/subjects are never interpreted as placeholders.
    import re
    values = {"name": name.split(" ")[0], "number": str(ticket.number), "subject": ticket.subject}
    return re.sub(r"\{(name|number|subject)\}", lambda m: values[m[1]], body)


async def text(db: AsyncSession, key: str, ticket, name: str) -> str:
    template = next(t for t in await templates(db) if t["key"] == key)
    return render(template["body"], ticket, name)
