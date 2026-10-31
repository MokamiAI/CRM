import uuid
from datetime import datetime

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, plan_feature, require_role
from app.api.email_dispatch import commit_and_enqueue
from app.core.database import CommitBeforeResponseRoute
from app.core.plans import TEAM_CHAT, WHATSAPP_SMS
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.messaging import (
    ChannelCreate,
    ChannelOut,
    ChannelUpdate,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    InboxCounts,
    MessageCreate,
    MessageOut,
    ReactionToggle,
    TeamMessageCreate,
    TeamMessageEdit,
    TeamMessageOut,
)
from app.services import ticket_attachments
from app.services.billing_service import BillingService
from app.services.channel_service import ChannelService
from app.services.messaging_service import MessagingService, reply_address
from app.tasks.messaging_tasks import send_conversation_message_task

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["messaging"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)


async def _detail(service: MessagingService, conversation) -> ConversationDetail:
    # Built from the plain columns plus an explicit message query: validating
    # the ORM object directly would lazy-load .messages, which async can't.
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        messages=[MessageOut.model_validate(m) for m in await service.messages(conversation.id)],
        reply_to_address=reply_address(conversation.token),
    ).model_copy(update={"customer_name": await service.customer_name(conversation)})


# ---------- Customer inbox ----------


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    status: str = Query("open", pattern="^(open|closed|all)$"),
    mine: bool = False,
    customer_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = await MessagingService(db).list_conversations(status, user.id if mine else None, customer_id)
    return [ConversationOut.model_validate(c).model_copy(update={"customer_name": name}) for c, name in rows]


@router.get("/conversations/counts", response_model=InboxCounts)
async def inbox_counts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await MessagingService(db).counts(user.id)


@router.get("/conversations/channels", response_model=dict[str, bool])
async def available_channels(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Which channels this company can message customers on (for everyone,
    not just admins: the composer offers only these)."""
    service = ChannelService(db)
    return {
        "email": True,
        "whatsapp": await service.enabled("whatsapp") is not None,
        "sms": await service.enabled("sms") is not None,
    }


@router.get("/conversations/inbox-address", response_model=dict)
async def company_inbox_address(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """The address customers can email to start a new conversation."""
    return {"address": await MessagingService(db).inbox_address_for_current()}


@router.post("/conversations", response_model=ConversationDetail, status_code=201)
async def start_conversation(data: ConversationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    if data.channel != "email":
        await BillingService(db).require_feature(WHATSAPP_SMS)
    service = MessagingService(db)
    conversation, message = await service.start(data, user)
    await commit_and_enqueue(db, send_conversation_message_task, str(message.id))
    return await _detail(service, conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = MessagingService(db)
    conversation = await service.get_conversation(conversation_id)
    await service.mark_read(conversation)
    return await _detail(service, conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID, data: ConversationUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    service = MessagingService(db)
    conversation = await service.update(conversation_id, data)
    return ConversationOut.model_validate(conversation).model_copy(update={"customer_name": await service.customer_name(conversation)})


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def post_message(
    conversation_id: uuid.UUID, data: MessageCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)
):
    service = MessagingService(db)
    if data.kind == "reply" and (await service.get_conversation(conversation_id)).channel != "email":
        await BillingService(db).require_feature(WHATSAPP_SMS)
    message = await service.post(conversation_id, data.body, data.kind, user)
    if message.direction == "out":
        await commit_and_enqueue(db, send_conversation_message_task, str(message.id))
    return message


# ---------- Team chat ----------


@router.get("/team-chat/channels", response_model=list[ChannelOut])
async def list_channels(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = MessagingService(db)
    return await service.channel_views(await service.channels(user))


@router.post("/team-chat/channels", response_model=ChannelOut, status_code=201, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def create_channel(data: ChannelCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    service = MessagingService(db)
    channel = await service.create_channel(data.name, user, data.member_ids)
    return (await service.channel_views([channel]))[0]


@router.patch("/team-chat/channels/{channel_id}", response_model=ChannelOut, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def update_channel(channel_id: uuid.UUID, data: ChannelUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    service = MessagingService(db)
    channel = await service.update_channel(channel_id, user, data.name, data.member_ids)
    return (await service.channel_views([channel]))[0]


@router.delete("/team-chat/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    await MessagingService(db).delete_channel(channel_id, user)


@router.get("/team-chat/channels/{channel_id}/messages", response_model=list[TeamMessageOut])
async def channel_messages(
    channel_id: uuid.UUID,
    after: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = MessagingService(db)
    messages = await service.team_messages(channel_id, user, after)
    await service.read_team_channel(channel_id, user)
    return await service.message_views(messages)


async def _one(service: MessagingService, message) -> dict:
    return (await service.message_views([message]))[0]


@router.post("/team-chat/channels/{channel_id}/messages", response_model=TeamMessageOut, status_code=201, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def post_team_message(
    channel_id: uuid.UUID, data: TeamMessageCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    # Viewers can chat with the team too; they just can't change records.
    service = MessagingService(db)
    message = await service.post_team_message(channel_id, data.body, user, data.reply_to_id, data.mention_ids)
    return await _one(service, message)


@router.post("/team-chat/channels/{channel_id}/messages/files", response_model=TeamMessageOut, status_code=201, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def post_team_files(
    channel_id: uuid.UUID,
    body: str = Form(default="", max_length=5_000),
    reply_to_id: uuid.UUID | None = Form(default=None),
    mention_ids: list[uuid.UUID] = Form(default=[]),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """A message with files (up to 5, 10 MB each), checked like ticket files."""
    service = MessagingService(db)
    attachments = await ticket_attachments.read_files(files)
    message = await service.post_team_message(channel_id, body, user, reply_to_id, mention_ids, attachments)
    return await _one(service, message)


@router.patch("/team-chat/messages/{message_id}", response_model=TeamMessageOut)
async def edit_team_message(message_id: uuid.UUID, data: TeamMessageEdit, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = MessagingService(db)
    return await _one(service, await service.edit_team_message(message_id, data.body, user))


@router.delete("/team-chat/messages/{message_id}", status_code=204)
async def delete_team_message(message_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await MessagingService(db).delete_team_message(message_id, user)


@router.post("/team-chat/messages/{message_id}/reactions", response_model=TeamMessageOut)
async def toggle_reaction(message_id: uuid.UUID, data: ReactionToggle, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    service = MessagingService(db)
    return await _one(service, await service.toggle_reaction(message_id, data.emoji, user))


@router.get("/team-chat/messages/{message_id}/attachments/{attachment_id}", include_in_schema=False)
async def team_file(message_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await MessagingService(db).team_file(message_id, attachment_id, user)
    return Response(row.data, media_type=row.content_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, no-store",
    })
