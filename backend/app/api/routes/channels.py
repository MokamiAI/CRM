"""Settings > Email / WhatsApp / SMS: each company connects its own accounts."""
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import WHATSAPP_SMS
from app.models.enums import UserRole
from app.models.messaging import CONNECTION_KINDS, ChannelConnection
from app.schemas.messaging import ConnectionOut, ConnectionSave, ConnectionTest
from app.services.billing_service import BillingService
from app.services.channel_service import ChannelService, spec_for, webhook_url

router = APIRouter(
    route_class=CommitBeforeResponseRoute,
    prefix="/settings/channels",
    tags=["settings"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)

Kind = Literal["email_in", "whatsapp", "sms"]


def verify_token(conn: ChannelConnection) -> str:
    # What the admin pastes into Meta's webhook "Verify token" box.
    return conn.webhook_token[:16]


def _out(service: ChannelService, kind: str, conn: ChannelConnection | None) -> ConnectionOut:
    if conn is None:
        return ConnectionOut(kind=kind)
    saved = service.secrets_of(conn)
    return ConnectionOut(
        kind=kind,
        provider=conn.provider,
        enabled=conn.enabled,
        settings={k: v for k, v in (conn.settings or {}).items() if k != "last_uid"},
        secrets_set={name: bool(saved.get(name)) for name in spec_for(conn.provider).secret_fields},
        webhook_url=webhook_url(conn),
        verify_token=verify_token(conn) if kind == "whatsapp" else None,
        status=conn.status,
        last_error=conn.last_error,
        last_checked_at=conn.last_checked_at,
    )


@router.get("", response_model=list[ConnectionOut])
async def list_channels(db: AsyncSession = Depends(get_db)):
    service = ChannelService(db)
    saved = {c.kind: c for c in await service.list()}
    return [_out(service, kind, saved.get(kind)) for kind in CONNECTION_KINDS]


@router.put("/{kind}", response_model=ConnectionOut)
async def save_channel(kind: Kind, data: ConnectionSave, db: AsyncSession = Depends(get_db)):
    if kind in ("whatsapp", "sms") and data.enabled:
        await BillingService(db).require_feature(WHATSAPP_SMS)
    service = ChannelService(db)
    conn = await service.save(kind, data.provider, data.enabled, data.settings, data.secrets)
    return _out(service, kind, conn)


@router.post("/{kind}/test", response_model=ConnectionOut)
async def test_channel(kind: Kind, data: ConnectionTest, db: AsyncSession = Depends(get_db)):
    service = ChannelService(db)
    conn = await service.test(kind, data.to)
    return _out(service, kind, conn)
