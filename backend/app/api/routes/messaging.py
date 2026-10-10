import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
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
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    InboxCounts,
    MessageCreate,
    MessageOut,
    TeamMessageCreate,
    TeamMessageOut,
)
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
    return await MessagingService(db).channels(user)


@router.post("/team-chat/channels", response_model=ChannelOut, status_code=201, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def create_channel(data: ChannelCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_can_write)):
    return await MessagingService(db).create_channel(data.name, user)


@router.get("/team-chat/channels/{channel_id}/messages", response_model=list[TeamMessageOut])
async def channel_messages(
    channel_id: uuid.UUID,
    after: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await MessagingService(db).team_messages(channel_id, after)


@router.post("/team-chat/channels/{channel_id}/messages", response_model=TeamMessageOut, status_code=201, dependencies=[Depends(plan_feature(TEAM_CHAT))])
async def post_team_message(
    channel_id: uuid.UUID, data: TeamMessageCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    # Viewers can chat with the team too; they just can't change records.
    return await MessagingService(db).post_team_message(channel_id, data.body, user)
