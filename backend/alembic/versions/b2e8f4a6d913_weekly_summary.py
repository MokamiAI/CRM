"""users.weekly_summary: the Monday summary email, on or off

NULL keeps the default (on for the account owner, off for the rest).

Revision ID: b2e8f4a6d913
Revises: a7d3e9f1c204
Create Date: 2026-11-21
"""
from alembic import op
import sqlalchemy as sa

revision = "b2e8f4a6d913"
down_revision = "a7d3e9f1c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("weekly_summary", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "weekly_summary")
