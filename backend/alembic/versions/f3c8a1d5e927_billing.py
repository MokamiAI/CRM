"""billing: subscriptions per company, payment history, Paystack plan codes

Existing companies start on the same free Grow trial as new sign-ups.

Revision ID: f3c8a1d5e927
Revises: e8b4c2f7a196
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "f3c8a1d5e927"
down_revision = "e8b4c2f7a196"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _company():
    return sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _company(),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(10), nullable=False),
        sa.Column("seats", sa.Integer, nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("paystack_customer_code", sa.String(50), nullable=True, index=True),
        sa.Column("paystack_plan_code", sa.String(50), nullable=True),
        sa.Column("paystack_subscription_code", sa.String(50), nullable=True, index=True),
        sa.Column("paystack_email_token", sa.String(100), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("company_id", name="uq_subscriptions_company"),
    )
    op.create_table(
        "billing_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _company(),
        sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(10), nullable=False),
        sa.Column("seats", sa.Integer, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "paystack_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(50), nullable=False, unique=True),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        *_timestamps(),
    )
    op.execute(
        """
        INSERT INTO subscriptions (id, company_id, plan, status, interval, seats, trial_ends_at)
        SELECT gen_random_uuid(), id, 'grow', 'trialing', 'monthly', 10, now() + interval '14 days'
        FROM company_settings
        """
    )


def downgrade() -> None:
    op.drop_table("paystack_plans")
    op.drop_table("billing_payments")
    op.drop_table("subscriptions")
