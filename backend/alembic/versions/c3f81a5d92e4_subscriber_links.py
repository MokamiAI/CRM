"""Subscribers in YGT's own pipeline: which prospect and deal stand for each company.

Revision ID: c3f81a5d92e4
Revises: b7e20d4a136f
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f81a5d92e4"
down_revision = "b7e20d4a136f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("subscriber_links",
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("deal_id", sa.UUID(), sa.ForeignKey("deals.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("subscriber_links")
