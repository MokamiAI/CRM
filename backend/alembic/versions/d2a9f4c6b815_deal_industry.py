"""deals: industry

Revision ID: d2a9f4c6b815
Revises: c6e1a4b7d283
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "d2a9f4c6b815"
down_revision = "c6e1a4b7d283"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("industry", sa.String(40), nullable=True))
    op.create_index("ix_deals_industry", "deals", ["industry"])


def downgrade() -> None:
    op.drop_index("ix_deals_industry", table_name="deals")
    op.drop_column("deals", "industry")
