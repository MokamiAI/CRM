"""company settings: automated invoice reminder schedule

Revision ID: 7c3e1a9b2f40
Revises: 1d88b9a5d6c2
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7c3e1a9b2f40"
down_revision = "1d88b9a5d6c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_settings",
        sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Days relative to the due date: negative = before, 0 = on the day,
    # positive = overdue by that many days.
    op.add_column(
        "company_settings",
        sa.Column(
            "reminder_offsets",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{-3,0,7,14}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "reminder_offsets")
    op.drop_column("company_settings", "reminders_enabled")
