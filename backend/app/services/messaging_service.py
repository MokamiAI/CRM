import re
import secrets
import uuid
from datetime import datetime, timezone
from email.utils import make_msgid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.tenancy import set_tenant
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.services.contact_service import account_email_matches
from app.models.messaging import Conversation, Message, TeamChannel, TeamMessage
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.messaging import ConversationCreate, ConversationUpdate, InboundEmail
from app.services.channel_providers import normalize_phone
from app.services.email_service import OutgoingEmail, render_email

_TOKEN_RE = re.compile(r"\b(reply|inbox)\+([A-Za-z0-9_-]{8,40})@", re.I)
# Where most mail clients start quoting the message being replied to.
_QUOTE_MARKERS = (
    re.compile(r"^On .{3,200} wrote:\s*$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^From: .+$", re.M),
    re.compile(r"^_{5,}\s*$", re.M),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _preview(body: str) -> str:
    return " ".join(body.split())[:200]


def strip_quoted(text: str) -> str:
    """The new part of an email reply: drops the quoted earlier message and
    the "On <date>, <name> wrote:" line most clients add above it."""
    cut = len(text)
    for marker in _QUOTE_MARKERS:
        match = marker.search(text)
        if match:
            cut = min(cut, match.start())
    lines = [line for line in text[:cut].splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip() or text.strip()


def reply_address(token: str) -> str:
    return f"reply+{token}@{settings.INBOUND_EMAIL_DOMAIN}"


def inbox_address(token: str) -> str:
    return f"inbox+{token}@{settings.INBOUND_EMAIL_DOMAIN}"


class CustomerNoEmailError(AppError):
    def __init__(self):
        super().__init__("Contact person's email not found. Add an email to their contact details.", "CUSTOMER_NO_EMAIL")


class CustomerNoPhoneError(AppError):
    def __init__(self):
        super().__init__("This customer has no valid phone number", "CUSTOMER_NO_PHONE")


class ChannelNotSetUpError(AppError):
    def __init__(self, channel: str):
        super().__init__(f"{channel} isn't set up yet: an admin can connect it in Settings", "CHANNEL_NOT_SET")


class MessagingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- Inbox ----------

    async def list_conversations(
        self, status: str = "open", assigned_to: uuid.UUID | None = None, customer_id: uuid.UUID | None = None
    ) -> list[tuple[Conversation, str | None]]:
        query = (
            select(Conversation, Customer.name)
            .outerjoin(Customer, Customer.id == Conversation.customer_id)
            .order_by(Conversation.last_message_at.desc())
            .limit(200)
        )
        if status != "all":
            query = query.where(Conversation.status == status)
        if assigned_to:
            query = query.where(Conversation.assigned_to == assigned_to)
        if customer_id:
            query = query.where(Conversation.customer_id == customer_id)
        return list((await self.db.execute(query)).tuples())

    async def counts(self, user_id: uuid.UUID) -> dict:
        row = (
            await self.db.execute(
                select(
                    func.count().filter(Conversation.unread.is_(True), Conversation.status == "open"),
                    func.count().filter(Conversation.status == "open"),
                    func.count().filter(Conversation.status == "open", Conversation.assigned_to == user_id),
                )
            )
        ).one()
        return {"unread": row[0], "open": row[1], "mine": row[2]}

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.db.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found", "CONVERSATION_NOT_FOUND")
        return conversation

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        query = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        return list((await self.db.scalars(query)).all())

    async def customer_name(self, conversation: Conversation) -> str | None:
        if conversation.customer_id is None:
            return None
        customer = await self.db.get(Customer, conversation.customer_id)
        return customer.name if customer else None

    def _add_message(self, conversation: Conversation, **values) -> Message:
        message = Message(conversation_id=conversation.id, created_at=_now(), **values)
        self.db.add(message)
        if values["direction"] != "note":
            conversation.last_message_at = message.created_at
            conversation.last_message_preview = _preview(values["body"])
        return message

    async def new_conversation(
        self,
        *,
        channel: str,
        customer: Customer | None,
        contact_name: str | None,
        subject: str,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        user: User | None = None,
    ) -> Conversation:
        conversation = Conversation(
            channel=channel,
            customer_id=customer.id if customer else None,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            subject=subject.strip()[:255],
            status="open",
            token=secrets.token_urlsafe(18),
            last_message_at=_now(),
            created_by=user.id if user else None,
            assigned_to=user.id if user else None,
        )
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    def add_inbound(
        self,
        conversation: Conversation,
        body: str,
        *,
        from_address: str,
        email_message_id: str | None = None,
        external_id: str | None = None,
    ) -> Message:
        """Files a message from the customer and flags the thread for the team."""
        message = self._add_message(
            conversation,
            direction="in",
            body=strip_quoted(body) if conversation.channel == "email" else body.strip(),
            from_email=from_address,
            status="received",
            email_message_id=email_message_id,
            external_id=external_id,
            sent_at=_now(),
        )
        conversation.unread = True
        conversation.status = "open"
        return message

    async def start(self, data: ConversationCreate, user: User) -> tuple[Conversation, Message]:
        from app.services.channel_service import ChannelService  # avoids an import cycle

        customer = await self.db.get(Customer, data.customer_id)
        if customer is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
        if data.channel == "email":
            to_email = data.to_email or customer.recipient_email
            if not to_email:
                raise CustomerNoEmailError()
            conversation = await self.new_conversation(
                channel="email", customer=customer, contact_name=customer.name,
                contact_email=str(to_email), subject=data.subject, user=user,
            )
        else:
            if await ChannelService(self.db).enabled(data.channel) is None:
                raise ChannelNotSetUpError(data.channel)
            phone = normalize_phone(data.to_phone or customer.phone)
            if not phone:
                raise CustomerNoPhoneError()
            label = "WhatsApp" if data.channel == "whatsapp" else "SMS"
            conversation = await self.new_conversation(
                channel=data.channel,
                customer=customer,
                contact_name=customer.name,
                contact_phone=phone,
                subject=data.subject or f"{label} with {customer.name}",
                user=user,
            )
        message = self._add_message(conversation, direction="out", body=data.body.strip(), author_id=user.id, status="queued")
        await self.db.flush()
        return conversation, message

    async def post(self, conversation_id: uuid.UUID, body: str, kind: str, user: User) -> Message:
        conversation = await self.get_conversation(conversation_id)
        if kind == "note":
            message = self._add_message(conversation, direction="note", body=body.strip(), author_id=user.id, status="sent", sent_at=_now())
        else:
            message = self._add_message(conversation, direction="out", body=body.strip(), author_id=user.id, status="queued")
            conversation.status = "open"
            conversation.unread = False
        await self.db.flush()
        return message

    async def update(self, conversation_id: uuid.UUID, data: ConversationUpdate) -> Conversation:
        conversation = await self.get_conversation(conversation_id)
        for name, value in data.model_dump(exclude_unset=True).items():
            setattr(conversation, name, value)
        await self.db.flush()
        return conversation

    async def mark_read(self, conversation: Conversation) -> None:
        if conversation.unread:
            conversation.unread = False
            await self.db.flush()

    async def inbox_address_for_current(self) -> str:
        company = await CompanySettingsRepository(self.db).get_current()
        if not company.inbox_token:
            company.inbox_token = secrets.token_urlsafe(12)
            await self.db.flush()
        return inbox_address(company.inbox_token)

    # ---------- Outgoing email ----------

    async def compose_outgoing(self, message: Message) -> OutgoingEmail:
        conversation = await self.get_conversation(message.conversation_id)
        company = await CompanySettingsRepository(self.db).get_for(conversation.company_id)
        author = await self.db.get(User, message.author_id) if message.author_id else None
        previous_in = await self.db.scalar(
            select(Message.email_message_id)
            .where(Message.conversation_id == conversation.id, Message.direction == "in", Message.email_message_id.is_not(None))
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        subject = conversation.subject if not previous_in else f"Re: {conversation.subject}"
        email = render_email(
            "conversation_message",
            to=conversation.contact_email,
            subject=subject,
            paragraphs=[block.split("\n") for block in message.body.split("\n\n") if block.strip()],
            author_name=author.full_name if author else company.company_name,
            signature=(author.email_signature if author else None) or company.email_signature,
            company=company,
        )
        from app.services.channel_service import ChannelService

        # The thread token rides in the Message-ID: replies quote it in
        # In-Reply-To/References, which is how a reply read from the
        # company's own mailbox finds its thread.
        domain = (company.sender_email or "").rpartition("@")[2] or settings.INBOUND_EMAIL_DOMAIN
        message.email_message_id = make_msgid(idstring=f"conv-{conversation.token}", domain=domain)
        email.headers["Message-ID"] = message.email_message_id
        if await ChannelService(self.db).enabled("email_in") is None:
            # No mailbox connected: fall back to the platform's reply address.
            email.headers["Reply-To"] = reply_address(conversation.token)
        if previous_in:
            email.headers["In-Reply-To"] = previous_in
            email.headers["References"] = previous_in
        return email

    # ---------- Incoming email (SYSTEM session) ----------

    async def receive(self, inbound: InboundEmail) -> Conversation | None:
        """Files an email from a customer. Runs before any company is known:
        the reply+/inbox+ token in the recipient address decides which
        company and thread it belongs to. Unknown tokens are dropped."""
        match = _TOKEN_RE.search(inbound.recipient)
        if not match:
            return None
        kind, token = match.group(1).lower(), match.group(2)
        if kind == "reply":
            conversation = await self.db.scalar(select(Conversation).where(Conversation.token == token))
            if conversation is None:
                return None
            set_tenant(self.db, conversation.company_id)
        else:
            company = await self.db.scalar(select(CompanySettings).where(CompanySettings.inbox_token == token))
            if company is None:
                return None
            set_tenant(self.db, company.id)
            customer = await self.db.scalar(
                select(Customer).where(account_email_matches(inbound.sender)).limit(1)
            )
            conversation = await self.new_conversation(
                channel="email",
                customer=customer,
                contact_name=customer.name if customer else (inbound.sender_name or None),
                contact_email=inbound.sender,
                subject=inbound.subject or "(no subject)",
            )
        self.add_inbound(conversation, inbound.text, from_address=inbound.sender, email_message_id=inbound.message_id)
        await self.db.flush()
        return conversation

    # ---------- Team chat ----------

    async def channels(self, user: User) -> list[TeamChannel]:
        channels = list((await self.db.scalars(select(TeamChannel).order_by(TeamChannel.created_at))).all())
        if not channels:
            general = TeamChannel(name="General", created_by=user.id)
            self.db.add(general)
            await self.db.flush()
            channels = [general]
        return channels

    async def create_channel(self, name: str, user: User) -> TeamChannel:
        channel = TeamChannel(name=name.strip(), created_by=user.id)
        self.db.add(channel)
        await self.db.flush()
        return channel

    async def _channel(self, channel_id: uuid.UUID) -> TeamChannel:
        channel = await self.db.get(TeamChannel, channel_id)
        if channel is None:
            raise NotFoundError("Channel not found", "CHANNEL_NOT_FOUND")
        return channel

    async def team_messages(self, channel_id: uuid.UUID, after: datetime | None = None) -> list[TeamMessage]:
        await self._channel(channel_id)
        query = select(TeamMessage).where(TeamMessage.channel_id == channel_id)
        if after:
            query = query.where(TeamMessage.created_at > after)
            return list((await self.db.scalars(query.order_by(TeamMessage.created_at))).all())
        latest = list((await self.db.scalars(query.order_by(TeamMessage.created_at.desc()).limit(200))).all())
        return latest[::-1]

    async def post_team_message(self, channel_id: uuid.UUID, body: str, user: User) -> TeamMessage:
        channel = await self._channel(channel_id)
        message = TeamMessage(channel_id=channel_id, author_id=user.id, body=body.strip(), created_at=_now())
        self.db.add(message)
        await self.db.flush()
        await self._tell_team(channel, message, user)
        return message

    async def _tell_team(self, channel: TeamChannel, message: TeamMessage, author: User) -> None:
        """Everyone else in the company hears about a new team message: in
        the bell and as an alert on their devices, not by email (a busy chat
        would flood inboxes). While unread, a channel's news is one
        notification that keeps the latest message and counts the rest."""
        from app.models.notification import Notification
        from app.services import notify

        key = f"team:{channel.id}"
        text = message.body if len(message.body) <= 140 else message.body[:139].rstrip() + "…"
        others = await self.db.scalars(select(User).where(
            User.company_id == author.company_id, User.id != author.id, User.is_active.is_(True)))
        for person in others.all():
            note = await self.db.scalar(select(Notification).where(Notification.user_id == person.id, Notification.key == key))
            count = note.params.get("count", 1) + 1 if note is not None and note.read_at is None else 1
            params = {"by": author.full_name, "channel": channel.name, "channel_id": str(channel.id), "count": count, "text": text}
            title = f"{count} new messages in #{channel.name}" if count > 1 else f"{author.full_name} in #{channel.name}"
            body = f"{author.full_name}: {text}"
            link = f"/messages?tab=team&ch={channel.id}"
            if note is None:
                await notify.notify(self.db, person, kind="team_message", title=title, body=body, link=link, params=params, key=key, email=False)
                continue
            note.params, note.title, note.body, note.link = params, title[:255], body, link
            note.read_at, note.created_at = None, _now()
            await self.db.commit()
            if notify.push_enabled():
                await notify._dispatch_push(note.id)

    async def read_team_channel(self, channel_id: uuid.UUID, user: User) -> None:
        """Opening a channel reads its notification."""
        from app.models.notification import Notification

        await self.db.execute(update(Notification).where(
            Notification.user_id == user.id, Notification.key == f"team:{channel_id}", Notification.read_at.is_(None)).values(read_at=_now()))
