# Every model module is imported here so Base.metadata is fully populated
# before Alembic autogenerate/upgrade runs (see alembic/env.py, which does
# `from app.models import *`).
from app.models.billing import BillingPayment, PaystackPlan, Subscription, SubscriptionInvoice
from app.models.company_settings import CompanySettings
from app.models.crm import Activity, ActivityAttachment, Contact, Deal, Note, TaskUpdate
from app.models.notification import Notification, PushSubscription
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
from app.models.purchasing import LineTemplate, PurchaseOrder, PurchaseOrderItem, Supplier
from app.models.quote import Quote, QuoteItem
from app.models.discovery import DiscoveredLead, DiscoverySettings
from app.models.recurring import RecurringInvoice
from app.models.reminder import ReminderLog
from app.models.user import RefreshToken, User

__all__ = [
    "PushSubscription",
    "Notification",
    "TaskUpdate",
    "ActivityAttachment",
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
    "SubscriptionInvoice",
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
    "LineTemplate",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "Supplier",
    "Quote",
    "RecurringInvoice",
    "DiscoveredLead",
    "DiscoverySettings",
    "QuoteItem",
    "ReminderLog",
    "Segment",
    "TeamChannel",
    "TeamMessage",
    "RefreshToken",
    "User",
]
