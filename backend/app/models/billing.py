import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


class Subscription(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A company's YGT plan. One row per company, created with a free trial
    when the company signs up; Paystack's webhook keeps it current.

    status: trialing | active | past_due | cancelled | free. What a company
    can actually use is worked out from this in billing_service.effective()."""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("company_id", name="uq_subscriptions_company"),)

    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    interval: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The period end the yearly renewal notice was sent for (CPA s14): once a year.
    renewal_notice_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paystack_customer_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    paystack_plan_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paystack_subscription_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # Paystack needs this alongside the code to cancel a subscription.
    paystack_email_token: Mapped[str | None] = mapped_column(String(100), nullable=True)


class BillingPayment(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """A successful subscription charge, for the company's payment history.
    The Paystack reference is unique, so a repeated webhook is ignored."""

    __tablename__ = "billing_payments"

    reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ZAR")
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubscriptionInvoice(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """YGT's invoice for one subscription payment, made the moment Paystack
    confirms it and emailed to the company. Numbered YGT-INV-000001 upwards,
    one per payment (the unique payment_id makes a repeated webhook a
    no-op). Seller and buyer details are copied in at the time, so a later
    change of address or VAT status never rewrites an issued invoice."""

    __tablename__ = "subscription_invoices"

    # An expired trial can issue an unpaid invoice before a payment exists.
    trial_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_paid(self) -> bool:
        return self.payment_id is not None

    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_payments.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    payment_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # what was paid, VAT included if any
    vat_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seller: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    buyer: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SubscriberLink(TimestampMixin, Base):
    """Which prospect and deal in YGT's own workspace stand for a company
    that signed up to YGT, and the subscription state last copied onto that
    deal (services/subscriber_pipeline.py). Platform-wide, not per company.
    The deal only moves when the state changes, so a stage someone sets by
    hand stays put until the subscription itself moves on."""

    __tablename__ = "subscriber_links"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_settings.id", ondelete="CASCADE"), primary_key=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    # The quote accepted at sign-up and the R0.00 trial invoice (both kept at
    # the seats in use until they pay), and the monthly invoice once they do.
    quote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True)
    trial_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("recurring_invoices.id", ondelete="SET NULL"), nullable=True)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PaystackPlan(UUIDPKMixin, TimestampMixin, Base):
    """Plans created in YGT's Paystack account, one per plan, interval and
    number of users (Paystack plans have a fixed amount). Platform-wide,
    not per company; created the first time someone chooses that option."""

    __tablename__ = "paystack_plans"

    # <account>:<plan>:<interval>:<users>, e.g. 3f9a1c2e:grow:monthly:5, where
    # <account> is a short hash of the secret key (test and live differ).
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
