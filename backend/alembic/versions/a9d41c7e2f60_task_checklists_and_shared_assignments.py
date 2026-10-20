"""Task checklists, shared assignments and reminder preferences.

Revision ID: a9d41c7e2f60
Revises: e50b7d9f2135
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a9d41c7e2f60"
down_revision = "e50b7d9f2135"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activities", sa.Column("checklist_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("activities", sa.Column("checklist", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("activities", sa.Column("assignee_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("activities", sa.Column("daily_reminders", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("activities", sa.Column("deadline_reminders", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    for column in ("deadline_reminders", "daily_reminders", "assignee_ids", "checklist", "checklist_enabled"):
        op.drop_column("activities", column)
