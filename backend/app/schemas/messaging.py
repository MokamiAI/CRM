import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ConversationCreate(BaseModel):
    customer_id: uuid.UUID
    channel: Literal["email", "whatsapp", "sms"] = "email"
    # Required for email; WhatsApp/SMS threads get a generated title.
    subject: str = Field(default="", max_length=255)
    body: str = Field(min_length=1, max_length=20_000)
    # Default to the customer's own email address / phone number.
    to_email: EmailStr | None = None
    to_phone: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _email_needs_subject(self):
        if self.channel == "email" and not self.subject.strip():
            raise ValueError("An email needs a subject")
        return self


class ConversationUpdate(BaseModel):
    status: Literal["open", "closed"] | None = None
    assigned_to: uuid.UUID | None = None
    unread: bool | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    # reply: emailed to the customer; note: internal, team only.
    kind: Literal["reply", "note"] = "reply"


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    body: str
    author_id: uuid.UUID | None
    from_email: str | None
    status: str
    error: str | None
    created_at: datetime
    sent_at: datetime | None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None = None
    channel: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    subject: str
    status: str
    assigned_to: uuid.UUID | None
    unread: bool
    last_message_at: datetime
    last_message_preview: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
    reply_to_address: str = ""


class InboxCounts(BaseModel):
    unread: int
    open: int
    mine: int


class InboundEmail(BaseModel):
    """What a mail provider's inbound webhook posts (normalised)."""

    sender: EmailStr = Field(alias="from")
    sender_name: str | None = None
    recipient: str = Field(alias="to", max_length=500)
    subject: str = Field(default="", max_length=500)
    text: str = Field(default="", max_length=100_000)
    message_id: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(populate_by_name=True)


# ---------- Team chat ----------


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    # Who can see the space, besides whoever creates it.
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    member_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    is_private: bool = False
    created_by: uuid.UUID | None = None
    # Private spaces only; an open channel is everyone's.
    member_ids: list[uuid.UUID] = Field(default_factory=list)
    # The whole team's first channel: can't be renamed into a space or deleted.
    is_general: bool = False


REACTIONS = ("👍", "❤️", "😂", "🎉", "🙏", "👀", "✅")


class TeamMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5_000)
    reply_to_id: uuid.UUID | None = None
    # People named with @ in the message: told directly.
    mention_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class TeamMessageEdit(BaseModel):
    body: str = Field(min_length=1, max_length=5_000)


class ReactionToggle(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class TeamAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size: int


class TeamReactionOut(BaseModel):
    emoji: str
    user_ids: list[uuid.UUID]


class TeamReplyOut(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None
    body: str


class TeamMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    reply_to_id: uuid.UUID | None = None
    reply_to: TeamReplyOut | None = None
    attachments: list[TeamAttachmentOut] = Field(default_factory=list)
    reactions: list[TeamReactionOut] = Field(default_factory=list)


# ---------- Channel connections (Settings) ----------


class ConnectionSave(BaseModel):
    provider: str = Field(max_length=30)
    enabled: bool = False
    # Non-secret values (hosts, ids, sender). Unknown keys are ignored.
    settings: dict[str, str | int | bool | None] = Field(default_factory=dict)
    # Only the secrets being changed; blank or missing keeps the saved one.
    secrets: dict[str, str] = Field(default_factory=dict)


class ConnectionTest(BaseModel):
    # WhatsApp/SMS: send a real test message to this number.
    to: str | None = Field(default=None, max_length=32)


class ConnectionOut(BaseModel):
    kind: str
    provider: str | None = None
    enabled: bool = False
    settings: dict = {}
    # Which secrets are saved (never their values).
    secrets_set: dict[str, bool] = {}
    webhook_url: str | None = None
    verify_token: str | None = None
    status: str = "not_set"
    last_error: str | None = None
    last_checked_at: datetime | None = None
