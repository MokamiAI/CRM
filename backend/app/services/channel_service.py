import re
import secrets as pysecrets
from datetime import datetime, timezone

from fastapi import status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_json, encrypt_json
from app.core.exceptions import AppError
from app.core.tenancy import set_tenant
from app.models.customer import Customer
from app.models.messaging import CONNECTION_KINDS, ChannelConnection, Conversation, Message
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services import channel_providers as providers
from app.services import email_inbox
from app.services.channel_providers import FieldSpec, InboundText, ProviderError, ProviderSpec, normalize_phone

IMAP = ProviderSpec(
    kind="email_in",
    fields=[
        FieldSpec("host"),
        FieldSpec("port", required=False),
        FieldSpec("username"),
        FieldSpec("password", secret=True),
        FieldSpec("use_ssl", required=False),
        FieldSpec("folder", required=False),
        FieldSpec("only_known_customers", required=False),
    ],
)
PROVIDERS_FOR_KIND = {"email_in": ["imap"], **providers.PROVIDERS_FOR}
_THREAD_TOKEN_RE = re.compile(r"conv-([A-Za-z0-9_-]{8,40})@")
_REPLY_ADDR_RE = re.compile(r"\breply\+([A-Za-z0-9_-]{8,40})@", re.I)


class ChannelError(AppError):
    def __init__(self, message: str, code: str = "CHANNEL_INVALID"):
        super().__init__(message, code, status.HTTP_422_UNPROCESSABLE_ENTITY)


def spec_for(provider: str) -> ProviderSpec:
    if provider == "imap":
        return IMAP
    if provider not in providers.PROVIDERS:
        raise ChannelError(f"Unknown provider {provider}")
    return providers.PROVIDERS[provider]["spec"]


def webhook_url(conn: ChannelConnection) -> str | None:
    if conn.kind == "email_in":
        return None
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/channels/{conn.webhook_token}/{conn.kind}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- Settings ----------

    async def get(self, kind: str) -> ChannelConnection | None:
        return await self.db.scalar(select(ChannelConnection).where(ChannelConnection.kind == kind))

    async def list(self) -> list[ChannelConnection]:
        return list((await self.db.scalars(select(ChannelConnection))).all())

    async def enabled(self, kind: str) -> ChannelConnection | None:
        conn = await self.get(kind)
        return conn if conn and conn.enabled else None

    async def save(self, kind: str, provider: str, enabled: bool, values: dict, new_secrets: dict) -> ChannelConnection:
        if kind not in CONNECTION_KINDS or provider not in PROVIDERS_FOR_KIND[kind]:
            raise ChannelError(f"{provider} can't be used for {kind}")
        spec = spec_for(provider)
        conn = await self.get(kind)
        if conn is None:
            conn = ChannelConnection(kind=kind, provider=provider, webhook_token=pysecrets.token_urlsafe(24), settings={})
            self.db.add(conn)
        # Switching provider drops the old provider's secrets.
        stored = decrypt_json(conn.secrets) if conn.provider == provider else {}
        for name in spec.secret_fields:
            value = (new_secrets.get(name) or "").strip()
            if value:
                stored[name] = value
        plain = {f.name: values.get(f.name) for f in spec.fields if not f.secret and values.get(f.name) not in (None, "")}
        if kind == "email_in" and "last_uid" in (conn.settings or {}) and conn.provider == provider:
            plain["last_uid"] = conn.settings["last_uid"]  # keep our place in the mailbox
        missing = [f.name for f in spec.fields if f.required and not (stored.get(f.name) if f.secret else plain.get(f.name))]
        if enabled and missing:
            raise ChannelError(f"Fill in: {', '.join(missing)}", "CHANNEL_INCOMPLETE")
        conn.provider, conn.enabled, conn.settings = provider, enabled, plain
        conn.secrets = encrypt_json(stored)
        conn.status, conn.last_error = "untested", None
        await self.db.flush()
        return conn

    def secrets_of(self, conn: ChannelConnection) -> dict:
        return decrypt_json(conn.secrets)

    async def test(self, kind: str, to: str | None = None) -> ChannelConnection:
        conn = await self.get(kind)
        if conn is None:
            raise ChannelError("Save the settings first", "CHANNEL_NOT_SET")
        creds = self.secrets_of(conn)
        try:
            if kind == "email_in":
                detail = await run_in_threadpool(email_inbox.test_mailbox, conn.settings, creds.get("password", ""))
            elif to:
                phone = normalize_phone(to)
                if not phone:
                    raise ProviderError("That phone number doesn't look right")
                company = await CompanySettingsRepository(self.db).get_current()
                await providers.PROVIDERS[conn.provider]["send"](
                    conn.settings, creds, phone, f"Test message from {company.company_name}: your CRM is connected."
                )
                detail = f"Test message sent to +{phone}"
            else:
                detail = await providers.PROVIDERS[conn.provider]["test"](conn.settings, creds)
        except (ProviderError, email_inbox.MailboxError) as exc:
            conn.status, conn.last_error = "error", str(exc)[:500]
        except KeyError as exc:
            conn.status, conn.last_error = "error", f"Missing setting: {exc.args[0]}"
        else:
            conn.status, conn.last_error = "ok", detail[:500]
        conn.last_checked_at = _now()
        await self.db.flush()
        return conn

    # ---------- Sending (WhatsApp / SMS) ----------

    async def send_text(self, conversation: Conversation, message: Message) -> str | None:
        conn = await self.enabled(conversation.channel)
        if conn is None:
            raise ProviderError(f"{conversation.channel} isn't set up in Settings")
        return await providers.PROVIDERS[conn.provider]["send"](conn.settings, self.secrets_of(conn), conversation.contact_phone, message.body)

    # ---------- Incoming (SYSTEM session) ----------

    async def connection_for_webhook(self, token: str, kind: str) -> ChannelConnection | None:
        conn = await self.db.scalar(
            select(ChannelConnection).where(ChannelConnection.webhook_token == token, ChannelConnection.kind == kind)
        )
        if conn is not None:
            set_tenant(self.db, conn.company_id)
        return conn

    async def _customer_by_phone(self, phone: str) -> Customer | None:
        candidates = (await self.db.scalars(select(Customer).where(Customer.phone.is_not(None)))).all()
        return next((c for c in candidates if normalize_phone(c.phone) == phone), None)

    async def receive_texts(self, conn: ChannelConnection, items: list[InboundText]) -> int:
        from app.services.messaging_service import MessagingService  # circular at import time

        filed = 0
        messaging = MessagingService(self.db)
        for item in items:
            phone = normalize_phone(item.from_phone)
            if not phone or not item.text:
                continue
            conversation = await self.db.scalar(
                select(Conversation)
                .where(Conversation.channel == conn.kind, Conversation.contact_phone == phone)
                .order_by(Conversation.last_message_at.desc())
                .limit(1)
            )
            if conversation is None:
                customer = await self._customer_by_phone(phone)
                label = "WhatsApp" if conn.kind == "whatsapp" else "SMS"
                conversation = await messaging.new_conversation(
                    channel=conn.kind,
                    customer=customer,
                    contact_name=customer.name if customer else (item.name or f"+{phone}"),
                    contact_phone=phone,
                    subject=f"{label} from {customer.name if customer else item.name or '+' + phone}",
                )
            messaging.add_inbound(conversation, item.text, from_address=f"+{phone}", external_id=item.external_id)
            filed += 1
        await self.db.flush()
        return filed

    async def poll_mailbox(self, conn: ChannelConnection) -> int:
        """Files new emails from the company's own mailbox. Session must be
        scoped to the connection's company."""
        from app.services.messaging_service import MessagingService

        password = self.secrets_of(conn).get("password", "")
        last_uid = (conn.settings or {}).get("last_uid")
        try:
            emails, top = await run_in_threadpool(email_inbox.fetch_new, conn.settings, password, last_uid)
        except email_inbox.MailboxError as exc:
            conn.status, conn.last_error, conn.last_checked_at = "error", str(exc)[:500], _now()
            await self.db.flush()
            return 0
        company = await CompanySettingsRepository(self.db).get_current()
        own = {(company.sender_email or "").lower(), (conn.settings.get("username") or "").lower()} - {""}
        only_known = conn.settings.get("only_known_customers", True) not in (False, "false", "0")
        messaging = MessagingService(self.db)
        filed = 0
        for mail in emails:
            if mail.sender in own:
                continue  # our own outgoing copies
            conversation = None
            token = _THREAD_TOKEN_RE.search(mail.references) or _REPLY_ADDR_RE.search(mail.recipients)
            if token:
                conversation = await self.db.scalar(select(Conversation).where(Conversation.token == token.group(1)))
            if conversation is None:
                customer = (
                    await self.db.scalars(select(Customer).where(Customer.email.ilike(mail.sender)).limit(1))
                ).first()
                if customer is None and only_known:
                    continue
                conversation = await messaging.new_conversation(
                    channel="email",
                    customer=customer,
                    contact_name=customer.name if customer else mail.sender_name,
                    contact_email=mail.sender,
                    subject=(mail.subject or "(no subject)")[:255],
                )
            messaging.add_inbound(conversation, mail.text, from_address=mail.sender, email_message_id=mail.message_id)
            filed += 1
        conn.settings = {**conn.settings, "last_uid": top}  # reassign: JSONB change tracking
        conn.status, conn.last_error, conn.last_checked_at = "ok", None, _now()
        await self.db.flush()
        return filed

