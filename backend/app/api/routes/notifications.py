"""The bell: a person's notifications, and the phones and computers they
let YGT push to. See app/services/notify.py."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.database import CommitBeforeResponseRoute
from app.models.notification import Notification, PushSubscription
from app.models.user import User
from app.services.notify import notify, push_enabled

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    params: dict
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


class ReadRequest(BaseModel):
    # None: all of them.
    ids: list[uuid.UUID] | None = None


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class PushSubscribe(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


async def _ask_marketing(db: AsyncSession, user: User) -> None:
    """Once, for people who signed up before YGT asked: may it send them
    tips, news and offers (POPIA s69)? In the app only: no email or push,
    since that would be the marketing they haven't agreed to."""
    if await db.scalar(select(Notification.id).where(Notification.user_id == user.id, Notification.key == "marketing_consent")):
        return
    try:
        async with db.begin_nested():
            db.add(Notification(
                company_id=user.company_id, user_id=user.id, kind="marketing_consent", key="marketing_consent", link="/",
                title="May YGT send you tips, news and offers?",
                body="Say yes or no on the notice at the top of YGT. You can change your mind at any time under your profile.",
            ))
            await db.flush()
    except IntegrityError:  # the bell asked at the same moment
        pass


@router.get("", response_model=NotificationList)
async def list_notifications(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The latest 40, newest first, and how many are unread."""
    if user.marketing_opt_in is None and not user.is_platform_admin:
        await _ask_marketing(db, user)
    rows =await db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(40))
    unread = await db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return NotificationList(unread=unread or 0, items=list(rows.all()))


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(data: ReadRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if data.ids is not None:
        stmt = stmt.where(Notification.id.in_(data.ids))
    await db.execute(stmt.values(read_at=datetime.now(timezone.utc)))


@router.get("/push")
async def push_settings():
    """The public key browsers need to subscribe; enabled is false until
    the server has its VAPID keys."""
    return {"enabled": push_enabled(), "public_key": settings.VAPID_PUBLIC_KEY or None}


@router.post("/push", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(data: PushSubscribe, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """This device agreed to push messages (or renewed its subscription)."""
    existing = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if existing is not None:
        # Same browser, maybe a different person signed in now: it's theirs.
        existing.user_id, existing.company_id = user.id, user.company_id
        existing.p256dh, existing.auth = data.keys.p256dh, data.keys.auth
    else:
        db.add(PushSubscription(company_id=user.company_id, user_id=user.id, endpoint=data.endpoint, p256dh=data.keys.p256dh, auth=data.keys.auth))
    await db.flush()


@router.post("/push/remove", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(data: PushEndpoint, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    sub = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint, PushSubscription.user_id == user.id))
    if sub is not None:
        await db.delete(sub)


@router.post("/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """"Send me a test": shows up behind the bell and on this person's devices."""
    await notify(
        db, user,
        kind="test",
        title="Notifications are on",
        body="This is how YGT will remind you about activities and tasks.",
        link="/activities",
        email=False,
    )
    return {"ok": True}
