# Every model module is imported here so Base.metadata is fully populated
# before Alembic autogenerate/upgrade runs (see alembic/env.py, which does
# `from app.models import *`).
from app.models.billing import BillingPayment, PaystackPlan, Subscription
from app.models.company_settings import CompanySettings
from app.models.crm import Activity, Contact, Deal, Note
from app.models.custom_field import CustomFieldDefinition
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceItem
from app.models.marketing import Campaign, CampaignRecipient, Segment
from app.models.messaging import ChannelConnection, Conversation, Message, TeamChannel, TeamMessage
from app.models.payment import Payment
from app.models.platform import (
    AuditEvent,
    BillingRefund,
    ContactRequest,
    ErrorLog,
    PasswordReset,
    PlatformSetting,
    SessionBooking,
    SupportTicket,
    TicketMessage,
)
from app.models.product import Product
from app.models.quote import Quote, QuoteItem
from app.models.reminder import ReminderLog
from app.models.user import RefreshToken, User

__all__ = [
    "Activity",
    "AuditEvent",
    "BillingRefund",
    "ContactRequest",
    "ErrorLog",
    "PasswordReset",
    "PlatformSetting",
    "SessionBooking",
    "SupportTicket",
    "TicketMessage",
    "BillingPayment",
    "Contact",
    "PaystackPlan",
    "Subscription",
    "Deal",
    "Note",
    "ChannelConnection",
    "CompanySettings",
    "Conversation",
    "CustomFieldDefinition",
    "Customer",
    "Campaign",
    "CampaignRecipient",
    "Invoice",
    "InvoiceItem",
    "Message",
    "Payment",
    "Product",
    "Quote",
    "QuoteItem",
    "ReminderLog",
    "Segment",
    "TeamChannel",
    "TeamMessage",
    "RefreshToken",
    "User",
]
