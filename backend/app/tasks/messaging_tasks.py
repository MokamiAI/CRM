# Sends a conversation reply to the customer. Queued by the inbox API after
# the message row is committed (see app/api/routes/messaging.py).
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from celery_app import celery_app

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.messaging import ChannelConnection, Conversation, Message
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.channel_providers import ProviderError
from app.services.channel_service import ChannelService
from app.services.email_service import EmailNotConfiguredError, send_email
from app.services.email_settings import resolve_email_config
from app.services.messaging_service import MessagingService
from app.tasks._runner import run_async

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.messaging_tasks.send_conversation_message_task",
    autoretry_for=(OSError,),
    retry_backoff=30,
    retry_backoff_max=30 * 60,
    max_retries=5,
)
def send_conversation_message_task(message_id: str) -> bool:
    async def _run() -> bool:
        async with AsyncSessionLocal() as session:
            set_system(session)
            message = await session.get(Message, uuid.UUID(message_id))
            if message is None or message.status != "queued":
                return False
            set_tenant(session, message.company_id)
            conversation = await session.get(Conversation, message.conversation_id)
            if conversation.channel in ("whatsapp", "sms"):
                try:
                    message.external_id = await ChannelService(session).send_text(conversation, message)
                except ProviderError as exc:
                    message.status, message.error = "failed", str(exc)[:255]
                    await session.commit()
                    return False
                message.status, message.error, message.sent_at = "sent", None, datetime.now(timezone.utc)
                await session.commit()
                logger.info("Sent %s message %s", conversation.channel, message_id)
                return True
            config = resolve_email_config(await CompanySettingsRepository(session).get_current())
            email = await MessagingService(session).compose_outgoing(message)
            try:
                send_email(config, email)
            except EmailNotConfiguredError:
                message.status, message.error = "failed", "Outgoing email is not configured"
                await session.commit()
                return False
            except OSError as exc:
                message.error = str(exc)[:255]
                await session.commit()
                raise  # retried with backoff
            message.status, message.error, message.sent_at = "sent", None, datetime.now(timezone.utc)
            await session.commit()
            logger.info("Sent conversation message %s to %s", message_id, email.to)
            return True

    return run_async(_run)


@celery_app.task(name="app.tasks.messaging_tasks.poll_mailboxes_task")
def poll_mailboxes_task() -> int:
    """Reads new customer emails from every company's connected mailbox."""

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            set_system(session)
            rows = (
                await session.execute(
                    select(ChannelConnection.id, ChannelConnection.company_id).where(
                        ChannelConnection.kind == "email_in", ChannelConnection.enabled.is_(True)
                    )
                )
            ).all()
        filed = 0
        for connection_id, company_id in rows:
            async with AsyncSessionLocal() as session:
                set_tenant(session, company_id)
                conn = await session.get(ChannelConnection, connection_id)
                filed += await ChannelService(session).poll_mailbox(conn)
                await session.commit()
        return filed

    return run_async(_run)
