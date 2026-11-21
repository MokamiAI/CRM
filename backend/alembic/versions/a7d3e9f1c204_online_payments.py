"""online payments: customers pay invoices through the company's own Paystack

Each row is one attempt to pay an invoice online. The company's Paystack
secret key lives in channel_connections (kind "payments"), encrypted like
the WhatsApp and SMS credentials, so that table needs no change.

Revision ID: a7d3e9f1c204
Revises: f1a4c8e2b693
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a7d3e9f1c204"
down_revision = "f1a4c8e2b693"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "online_payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("channel", sa.String(30), nullable=True),
        sa.Column("payment_id", UUID, sa.ForeignKey("payments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("online_payments")
