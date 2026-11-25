"""Payment reminders on WhatsApp, as well as by email.

Meta only lets a business start a WhatsApp conversation (more than 24 hours
after the customer last wrote) with a message template it has approved.
So the company presses "Create reminder templates" once (Settings >
WhatsApp); YGT submits two templates to Meta on the company's own WhatsApp
Business account, and once Meta approves them, every payment reminder
also goes out on WhatsApp: with a "Pay now" button when online payments
are on, without one otherwise. Meta bills the company per message.

Each reminder sent is filed under Messages, in the customer's WhatsApp
conversation, so a reply lands in the same thread.
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import status
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.messaging import ChannelConnection, Conversation
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services import channel_providers as providers
from app.services.channel_providers import ProviderError, company_dial, normalize_phone
from app.services.channel_service import ChannelService
from app.services.online_payment_service import PAYABLE, OnlinePaymentService, amount_due, pay_token

logger = logging.getLogger(__name__)

LANGUAGE = "en"
WITH_BUTTON = "ygt_payment_reminder_pay"
PLAIN = "ygt_payment_reminder"
NAMES = (WITH_BUTTON, PLAIN)
_BODY = (
    "Hi {{1}}, this is a reminder from {{2}}: invoice {{3}} for {{4}} (due date: {{5}}) is still open. "
    "If you've already paid, thank you, and please ignore this message."
)
_EXAMPLE = ["Thandi", "Sizwe Builders", "INV-0053", "ZAR 1,150.00", "04 Dec 2026"]
# How long a template status is trusted before asking Meta again.
_RECHECK = timedelta(hours=1)


class WhatsAppSetupError(AppError):
    def __init__(self, message: str, code: str = "WHATSAPP_SETUP"):
        super().__init__(message, code, status.HTTP_422_UNPROCESSABLE_ENTITY)


def pay_base_url() -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/pay/"


def templates() -> list[dict]:
    """The two templates, as Meta's API takes them (category UTILITY: about
    an invoice the customer already has, not marketing)."""
    body = {"type": "BODY", "text": _BODY, "example": {"body_text": [_EXAMPLE]}}
    button = {
        "type": "BUTTONS",
        "buttons": [{"type": "URL", "text": "Pay now", "url": pay_base_url() + "{{1}}", "example": [pay_base_url() + "0" * 32 + "A" * 22]}],
    }
    pay_body = {**body, "text": _BODY.replace(" If you've", " You can pay online with the button below. If you've")}
    return [
        {"name": WITH_BUTTON, "language": LANGUAGE, "category": "UTILITY", "components": [pay_body, button]},
        {"name": PLAIN, "language": LANGUAGE, "category": "UTILITY", "components": [body]},
    ]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(currency: str, amount) -> str:
    return f"{currency} {Decimal(amount):,.2f}"


class WhatsAppReminderService:
    """Acts for one company: the session must be scoped to it."""

    def __init__(self, db):
        self.db = db
        self.channels = ChannelService(db)

    async def _connection(self) -> ChannelConnection:
        conn = await self.channels.get("whatsapp")
        if conn is None or conn.provider != "meta":
            raise WhatsAppSetupError("Connect WhatsApp first (Settings > WhatsApp).", "WHATSAPP_NOT_SET")
        return conn

    def _store(self, conn: ChannelConnection, statuses: dict[str, str]) -> dict:
        saved = {**(conn.settings or {}).get("templates", {})}
        for name in NAMES:
            if name in statuses:
                saved[name] = statuses[name]
        saved["checked_at"] = _now().isoformat()
        conn.settings = {**(conn.settings or {}), "templates": saved}  # reassign: JSONB change tracking
        return saved

    async def register(self, pin: str) -> None:
        conn = await self._connection()
        if not (pin.isdigit() and len(pin) == 6):
            raise WhatsAppSetupError("The PIN is 6 digits.", "WHATSAPP_PIN")
        try:
            await providers.meta_register(conn.settings, self.channels.secrets_of(conn), pin)
        except (ProviderError, KeyError) as exc:
            raise WhatsAppSetupError(f"Meta didn't register the number: {exc}", "WHATSAPP_REGISTER") from exc

    async def create_templates(self) -> dict:
        conn = await self._connection()
        if not (conn.settings or {}).get("business_account_id"):
            raise WhatsAppSetupError("Fill in the WhatsApp Business Account ID first (Meta: WhatsApp > API Setup), then save.", "WHATSAPP_WABA")
        secrets = self.channels.secrets_of(conn)
        try:
            for template in templates():
                await providers.meta_create_template(conn.settings, secrets, template)
            statuses = await providers.meta_template_statuses(conn.settings, secrets)
        except ProviderError as exc:
            raise WhatsAppSetupError(f"Meta didn't accept the templates: {exc}", "WHATSAPP_TEMPLATES") from exc
        saved = self._store(conn, statuses)
        await self.db.flush()
        return saved

    async def refresh(self) -> dict:
        conn = await self._connection()
        if not (conn.settings or {}).get("business_account_id"):
            return (conn.settings or {}).get("templates", {})
        try:
            statuses = await providers.meta_template_statuses(conn.settings, self.channels.secrets_of(conn))
        except ProviderError as exc:
            raise WhatsAppSetupError(f"Couldn't ask Meta: {exc}", "WHATSAPP_TEMPLATES") from exc
        saved = self._store(conn, statuses)
        await self.db.flush()
        return saved

    async def _approved(self, conn: ChannelConnection, name: str) -> bool:
        saved = (conn.settings or {}).get("templates", {})
        if saved.get(name) == "APPROVED":
            return True
        checked = saved.get("checked_at")
        if saved.get(name) and checked and _now() - datetime.fromisoformat(checked) < _RECHECK:
            return False
        try:
            saved = self._store(conn, await providers.meta_template_statuses(conn.settings, self.channels.secrets_of(conn)))
        except (ProviderError, KeyError):
            return False
        return saved.get(name) == "APPROVED"

    async def send_reminder(self, invoice_id) -> str:
        """Sends one reminder for the invoice if this company sends them on
        WhatsApp. Returns what happened, for the logs: never raises for a
        reason that's the company's setup or the customer's details."""
        conn = await self.channels.enabled("whatsapp")
        if conn is None or conn.provider != "meta" or (conn.settings or {}).get("payment_reminders") not in (True, "true", "1"):
            return "off"
        invoice = await self.db.get(Invoice, invoice_id)
        if invoice is None or invoice.status not in PAYABLE or amount_due(invoice) <= 0:
            return "nothing due"
        customer = await self.db.get(Customer, invoice.customer_id)
        company = await CompanySettingsRepository(self.db).get_current()
        phone = normalize_phone(customer.phone if customer else None, company_dial(company))
        if not phone:
            return "no phone"
        link = await OnlinePaymentService(self.db).pay_url_for(invoice)
        name = WITH_BUTTON if link else PLAIN
        if not await self._approved(conn, name):
            await self.db.flush()
            return "template not approved"
        currency = (company.default_currency or "ZAR").upper()
        values = [customer.name, company.company_name, invoice.invoice_number, _money(currency, amount_due(invoice)), f"{invoice.due_date:%d %b %Y}"]
        try:
            message_id = await providers.meta_send_template(
                conn.settings, self.channels.secrets_of(conn), phone, name, LANGUAGE, values, pay_token(invoice.id) if link else None
            )
        except ProviderError as exc:
            logger.warning("WhatsApp reminder for %s failed: %s", invoice.invoice_number, exc)
            return f"failed: {exc}"
        await self._file(customer, phone, invoice, values, link, message_id)
        return "sent"

    async def _file(self, customer: Customer, phone: str, invoice: Invoice, values: list[str], link: str | None, message_id: str | None) -> None:
        """Into Messages, in the customer's WhatsApp thread."""
        from app.services.messaging_service import MessagingService

        messaging = MessagingService(self.db)
        conversation = await self.db.scalar(
            select(Conversation)
            .where(Conversation.channel == "whatsapp", Conversation.contact_phone == phone)
            .order_by(Conversation.last_message_at.desc())
            .limit(1)
        )
        if conversation is None:
            conversation = await messaging.new_conversation(
                channel="whatsapp", customer=customer, contact_name=customer.name, contact_phone=phone, subject=f"WhatsApp with {customer.name}"
            )
        text = _BODY
        for index, value in enumerate(values, start=1):
            text = text.replace("{{%d}}" % index, value)
        if link:
            text += f"\n\nPay now: {link}"
        messaging._add_message(conversation, direction="out", body=f"Payment reminder for {invoice.invoice_number}\n\n{text}", status="sent", external_id=message_id, sent_at=_now())
        await self.db.flush()
