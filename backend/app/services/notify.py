"""Telling a person something: a reminder that an activity is due, a task
assigned to them, an update on a task they handed out.

Every notification goes three ways: listed behind the bell in the app,
emailed (from YGT's own address, see platform_email), and pushed to each
phone or computer the person allowed (Web Push; skipped until the server
has VAPID keys). A `key` makes it happen once, however often the
per-minute check (app/tasks/notification_tasks.py) runs."""
import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import Notification, PushSubscription
from app.models.user import User
from app.services import platform_email

logger = logging.getLogger(__name__)


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


async def notify(
    db: AsyncSession,
    user: User,
    *,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    params: dict | None = None,
    key: str | None = None,
    email: bool = True,
) -> Notification | None:
    """Records the notification and sends it on (commits). Returns None if
    this key was already sent to this person."""
    if not user.is_active:
        return None
    if key is not None:
        seen = await db.scalar(select(Notification.id).where(Notification.user_id == user.id, Notification.key == key))
        if seen is not None:
            return None
    note = Notification(
        company_id=user.company_id, user_id=user.id, kind=kind, title=title[:255], body=body, link=link, params=params or {}, key=key
    )
    try:
        async with db.begin_nested():
            db.add(note)
            await db.flush()
    except IntegrityError:  # sent by a check running at the same moment
        return None
    if email and user.email:
        paragraphs = [f"Hi {user.full_name.split(' ')[0]},"] + ([body] if body else [])
        message = platform_email.compose(
            to=user.email,
            subject=title,
            title=title,
            paragraphs=paragraphs,
            button=("Open in YGT", platform_email.app_link(link or "/")),
        )
        await platform_email.queue(db, message)  # commits
    else:
        await db.commit()
    if push_enabled():
        await _dispatch_push(note.id)
    return note


async def _dispatch_push(notification_id: uuid.UUID) -> None:
    """On the server, the worker sends it. Working locally without Redis,
    send it here (there's no worker to pick it up)."""
    from app.tasks.notification_tasks import send_push_task

    if settings.REDIS_URL.startswith("memory"):
        await send_push(notification_id)
        return
    try:
        from fastapi.concurrency import run_in_threadpool

        await run_in_threadpool(send_push_task.delay, str(notification_id))
    except Exception:
        logger.exception("Could not queue push for notification %s", notification_id)


async def send_push(notification_id: uuid.UUID) -> int:
    """Pushes one notification to each of its person's devices; forgets
    devices the push service says are gone. Returns how many it reached."""
    import asyncio

    from pywebpush import WebPushException, webpush

    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system

    async with AsyncSessionLocal() as db:
        set_system(db)
        note = await db.get(Notification, notification_id)
        if note is None:
            return 0
        subs = (await db.scalars(select(PushSubscription).where(PushSubscription.user_id == note.user_id))).all()
        payload = json.dumps({"title": note.title, "body": note.body or "", "url": note.link or "/", "tag": str(note.id)})
        sent = 0
        for sub in subs:
            info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_SUBJECT},
                    ttl=3600,
                )
                sent += 1
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):  # unsubscribed or expired: stop trying
                    await db.delete(sub)
                else:
                    logger.warning("Push to %s failed: %s", sub.endpoint[:60], exc)
            except Exception:
                logger.exception("Push to %s failed", sub.endpoint[:60])
        await db.commit()
        return sent
