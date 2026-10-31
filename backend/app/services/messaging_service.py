import re
import secrets
import uuid
from datetime import datetime, timezone
from email.utils import make_msgid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.tenancy import set_tenant
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.services.contact_service import account_email_matches
from app.models.enums import UserRole
from app.models.messaging import Conversation, Message, TeamChannel, TeamChannelMember, TeamMessage, TeamMessageAttachment, TeamMessageReaction
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.messaging import ConversationCreate, ConversationUpdate, InboundEmail
from app.services.channel_providers import normalize_phone
from app.services.email_service import OutgoingEmail, render_email
from app.services.signatures import signature_for

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
            signature=signature_for(author, company),
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
    # The whole team's General (the company's first channel) and any channel
    # from before spaces are open to everyone; a space (is_private) is seen
    # only by its members.

    async def _general_id(self) -> uuid.UUID | None:
        return await self.db.scalar(select(TeamChannel.id).order_by(TeamChannel.created_at, TeamChannel.id).limit(1))

    async def _member_ids(self, channel_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
        found: dict[uuid.UUID, list[uuid.UUID]] = {c: [] for c in channel_ids}
        if channel_ids:
            rows = await self.db.execute(
                select(TeamChannelMember.channel_id, TeamChannelMember.user_id).where(TeamChannelMember.channel_id.in_(channel_ids))
            )
            for channel_id, user_id in rows.all():
                found[channel_id].append(user_id)
        return found

    async def channel_views(self, channels: list[TeamChannel]) -> list[dict]:
        general = await self._general_id()
        members = await self._member_ids([c.id for c in channels if c.is_private])
        return [
            {
                "id": c.id, "name": c.name, "created_at": c.created_at, "is_private": c.is_private, "created_by": c.created_by,
                "member_ids": members.get(c.id, []), "is_general": c.id == general,
            }
            for c in channels
        ]

    async def _ensure_general(self, user: User) -> None:
        if await self._general_id() is None:
            self.db.add(TeamChannel(name="General", created_by=user.id))
            await self.db.flush()

    async def channels(self, user: User) -> list[TeamChannel]:
        await self._ensure_general(user)
        mine = select(TeamChannelMember.channel_id).where(TeamChannelMember.user_id == user.id)
        query = select(TeamChannel).where(TeamChannel.is_private.is_(False) | TeamChannel.id.in_(mine))
        return list((await self.db.scalars(query.order_by(TeamChannel.created_at, TeamChannel.id))).all())

    async def _valid_members(self, member_ids, user: User) -> set[uuid.UUID]:
        wanted = set(member_ids) | {user.id}
        found = await self.db.scalars(
            select(User.id).where(User.company_id == user.company_id, User.is_active.is_(True), User.id.in_(wanted))
        )
        return set(found.all()) | {user.id}

    async def create_channel(self, name: str, user: User, member_ids=()) -> TeamChannel:
        """A new space, seen by the people chosen for it. Scale has as many
        as it likes; Grow has one besides General (channels made before
        spaces keep working, they just count)."""
        from app.core.plans import GROW_SPACES, TEAM_SPACES
        from app.services.billing_service import BillingService, PlanLimitError

        await self._ensure_general(user)
        plan = (await BillingService(self.db).current()).plan
        if TEAM_SPACES not in plan.features:
            total = await self.db.scalar(select(func.count()).select_from(TeamChannel)) or 0
            if total - 1 >= GROW_SPACES:  # General doesn't count
                raise PlanLimitError("Your plan includes one space besides General. Scale has as many as you need.", "PLAN_TEAM_SPACES")
        channel = TeamChannel(name=name.strip(), created_by=user.id, is_private=True)
        self.db.add(channel)
        await self.db.flush()
        for member in await self._valid_members(member_ids, user):
            self.db.add(TeamChannelMember(channel_id=channel.id, user_id=member))
        await self.db.flush()
        return channel

    def _can_manage(self, channel: TeamChannel, user: User) -> bool:
        return channel.created_by == user.id or user.role in (UserRole.ADMIN, UserRole.MANAGER)

    async def update_channel(self, channel_id: uuid.UUID, user: User, name: str | None = None, member_ids=None) -> TeamChannel:
        channel = await self._channel(channel_id, user)
        if not self._can_manage(channel, user):
            raise AppError("Only whoever made this space, or a manager, can change it", "CHANNEL_FORBIDDEN", 403)
        if name is not None:
            channel.name = name.strip()
        if member_ids is not None:
            if not channel.is_private:
                raise AppError("Everyone on the team is in this channel", "CHANNEL_OPEN", 422)
            keep = await self._valid_members(member_ids, user)
            if channel.created_by:
                keep.add(channel.created_by)
            current = set((await self._member_ids([channel.id]))[channel.id])
            for gone in current - keep:
                await self.db.execute(
                    delete(TeamChannelMember).where(TeamChannelMember.channel_id == channel.id, TeamChannelMember.user_id == gone)
                )
            for added in keep - current:
                self.db.add(TeamChannelMember(channel_id=channel.id, user_id=added))
        await self.db.flush()
        return channel

    async def delete_channel(self, channel_id: uuid.UUID, user: User) -> None:
        """Deletes a space with its messages and files. General stays."""
        channel = await self._channel(channel_id, user)
        if channel.id == await self._general_id():
            raise AppError("General is the whole team's channel and stays", "CHANNEL_GENERAL", 422)
        if not self._can_manage(channel, user):
            raise AppError("Only whoever made this space, or a manager, can delete it", "CHANNEL_FORBIDDEN", 403)
        await self.db.delete(channel)
        await self.db.flush()

    async def _channel(self, channel_id: uuid.UUID, user: User | None = None) -> TeamChannel:
        channel = await self.db.get(TeamChannel, channel_id)
        if channel is not None and channel.is_private and user is not None:
            member = await self.db.scalar(
                select(TeamChannelMember.id).where(TeamChannelMember.channel_id == channel.id, TeamChannelMember.user_id == user.id)
            )
            if member is None:
                channel = None  # not theirs to see, so not there
        if channel is None:
            raise NotFoundError("Channel not found", "CHANNEL_NOT_FOUND")
        return channel

    async def team_messages(self, channel_id: uuid.UUID, user: User, after: datetime | None = None) -> list[TeamMessage]:
        await self._channel(channel_id, user)
        query = select(TeamMessage).where(TeamMessage.channel_id == channel_id)
        if after:
            query = query.where(TeamMessage.created_at > after)
            return list((await self.db.scalars(query.order_by(TeamMessage.created_at))).all())
        latest = list((await self.db.scalars(query.order_by(TeamMessage.created_at.desc()).limit(200))).all())
        return latest[::-1]

    async def message_views(self, messages: list[TeamMessage]) -> list[dict]:
        """Messages with their files, reactions and the message each replies to."""
        ids = [m.id for m in messages]
        files: dict[uuid.UUID, list] = {i: [] for i in ids}
        reactions: dict[uuid.UUID, dict[str, list]] = {i: {} for i in ids}
        quoted: dict[uuid.UUID, TeamMessage] = {}
        if ids:
            rows = await self.db.scalars(
                select(TeamMessageAttachment).where(TeamMessageAttachment.message_id.in_(ids)).order_by(TeamMessageAttachment.created_at)
            )
            for row in rows:
                files[row.message_id].append(row)
            rows = await self.db.execute(
                select(TeamMessageReaction.message_id, TeamMessageReaction.emoji, TeamMessageReaction.user_id)
                .where(TeamMessageReaction.message_id.in_(ids))
                .order_by(TeamMessageReaction.id)
            )
            for message_id, emoji, user_id in rows.all():
                reactions[message_id].setdefault(emoji, []).append(user_id)
            wanted = {m.reply_to_id for m in messages if m.reply_to_id}
            if wanted:
                quoted = {m.id: m for m in await self.db.scalars(select(TeamMessage).where(TeamMessage.id.in_(wanted)))}
        views = []
        for m in messages:
            original = quoted.get(m.reply_to_id) if m.reply_to_id else None
            views.append({
                "id": m.id, "channel_id": m.channel_id, "author_id": m.author_id, "body": m.body, "created_at": m.created_at,
                "edited_at": m.edited_at, "reply_to_id": m.reply_to_id,
                "reply_to": {"id": original.id, "author_id": original.author_id, "body": original.body[:200]} if original else None,
                "attachments": files[m.id],
                "reactions": [{"emoji": e, "user_ids": who} for e, who in reactions[m.id].items()],
            })
        return views

    async def post_team_message(
        self, channel_id: uuid.UUID, body: str, user: User, reply_to_id: uuid.UUID | None = None, mention_ids=(), files=()
    ) -> TeamMessage:
        channel = await self._channel(channel_id, user)
        body = (body or "").strip()
        if not body and not files:
            raise AppError("Write a message or attach a file", "MESSAGE_EMPTY", 422)
        if reply_to_id is not None:
            original = await self.db.get(TeamMessage, reply_to_id)
            if original is None or original.channel_id != channel.id:
                reply_to_id = None
        message = TeamMessage(channel_id=channel_id, author_id=user.id, body=body, created_at=_now(), reply_to_id=reply_to_id)
        self.db.add(message)
        await self.db.flush()
        for f in files:
            self.db.add(TeamMessageAttachment(message_id=message.id, **f))
        await self.db.flush()
        await self._tell_team(channel, message, user, set(mention_ids), [f["filename"] for f in files])
        return message

    async def _message(self, message_id: uuid.UUID, user: User) -> TeamMessage:
        message = await self.db.get(TeamMessage, message_id)
        if message is None:
            raise NotFoundError("Message not found", "MESSAGE_NOT_FOUND")
        await self._channel(message.channel_id, user)
        return message

    async def _own_message(self, message_id: uuid.UUID, user: User, allow_admin: bool = False) -> TeamMessage:
        message = await self._message(message_id, user)
        if message.author_id != user.id and not (allow_admin and user.role == UserRole.ADMIN):
            raise AppError("You can only change your own messages", "MESSAGE_FORBIDDEN", 403)
        return message

    async def edit_team_message(self, message_id: uuid.UUID, body: str, user: User) -> TeamMessage:
        message = await self._own_message(message_id, user)
        message.body = body.strip()
        message.edited_at = _now()
        await self.db.flush()
        return message

    async def delete_team_message(self, message_id: uuid.UUID, user: User) -> None:
        # An admin can take down anyone's message; its files go with it.
        await self.db.delete(await self._own_message(message_id, user, allow_admin=True))
        await self.db.flush()

    async def toggle_reaction(self, message_id: uuid.UUID, emoji: str, user: User) -> TeamMessage:
        from app.schemas.messaging import REACTIONS

        if emoji not in REACTIONS:
            raise AppError("Pick one of the reactions", "REACTION_UNKNOWN", 422)
        message = await self._message(message_id, user)
        mine = await self.db.scalar(select(TeamMessageReaction).where(
            TeamMessageReaction.message_id == message_id, TeamMessageReaction.user_id == user.id, TeamMessageReaction.emoji == emoji
        ))
        if mine is None:
            self.db.add(TeamMessageReaction(message_id=message_id, user_id=user.id, emoji=emoji))
        else:
            await self.db.delete(mine)
        await self.db.flush()
        return message

    async def team_file(self, message_id: uuid.UUID, attachment_id: uuid.UUID, user: User) -> TeamMessageAttachment:
        await self._message(message_id, user)
        row = await self.db.scalar(
            select(TeamMessageAttachment)
            .where(TeamMessageAttachment.id == attachment_id, TeamMessageAttachment.message_id == message_id)
            .options(undefer(TeamMessageAttachment.data))
        )
        if row is None:
            raise NotFoundError("File not found", "ATTACHMENT_NOT_FOUND")
        return row

    async def _tell_team(self, channel: TeamChannel, message: TeamMessage, author: User, mentioned=frozenset(), filenames=()) -> None:
        """Everyone else who can see the channel hears about a new message: in
        the bell and as an alert on their devices, not by email (a busy chat
        would flood inboxes). While unread, a channel's news is one
        notification that keeps the latest message and counts the rest.
        Someone named with @ gets a notification of their own instead."""
        from app.models.notification import Notification
        from app.services import notify

        key = f"team:{channel.id}"
        said = message.body or "📎 " + ", ".join(filenames)
        text = said if len(said) <= 140 else said[:139].rstrip() + "…"
        query = select(User).where(User.company_id == author.company_id, User.id != author.id, User.is_active.is_(True))
        if channel.is_private:
            query = query.where(User.id.in_(select(TeamChannelMember.user_id).where(TeamChannelMember.channel_id == channel.id)))
        link = f"/messages?tab=team&ch={channel.id}"
        for person in (await self.db.scalars(query)).all():
            if person.id in mentioned:
                params = {"by": author.full_name, "channel": channel.name, "channel_id": str(channel.id), "text": text}
                await notify.notify(
                    self.db, person, kind="team_mention", title=f"{author.full_name} mentioned you in #{channel.name}",
                    body=f"{author.full_name}: {text}", link=link, params=params, key=f"mention:{message.id}", email=False,
                )
                continue
            note = await self.db.scalar(select(Notification).where(Notification.user_id == person.id, Notification.key == key))
            count = note.params.get("count", 1) + 1 if note is not None and note.read_at is None else 1
            params = {"by": author.full_name, "channel": channel.name, "channel_id": str(channel.id), "count": count, "text": text}
            title = f"{count} new messages in #{channel.name}" if count > 1 else f"{author.full_name} in #{channel.name}"
            body = f"{author.full_name}: {text}"
            if note is None:
                await notify.notify(self.db, person, kind="team_message", title=title, body=body, link=link, params=params, key=key, email=False)
                continue
            note.params, note.title, note.body, note.link = params, title[:255], body, link
            note.read_at, note.created_at = None, _now()
            await self.db.commit()
            if notify.push_enabled():
                await notify._dispatch_push(note.id)

    async def read_team_channel(self, channel_id: uuid.UUID, user: User) -> None:
        """Opening a channel reads its notifications, mentions too."""
        from app.models.notification import Notification

        link = f"/messages?tab=team&ch={channel_id}"
        await self.db.execute(update(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None),
            (Notification.key == f"team:{channel_id}") | ((Notification.kind == "team_mention") & (Notification.link == link)),
        ).values(read_at=_now()))
