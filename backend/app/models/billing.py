from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
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
