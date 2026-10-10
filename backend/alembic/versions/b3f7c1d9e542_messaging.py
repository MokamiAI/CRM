"""messaging: customer conversations (two-way email) and team chat

Revision ID: b3f7c1d9e542
Revises: a8d2e6f19c37
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b3f7c1d9e542"
down_revision = "a8d2e6f19c37"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _company():
    return sa.Column("company_id", UUID, sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True)


def _user(name):
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("inbox_token", sa.String(40), nullable=True))
    op.create_unique_constraint("uq_company_settings_inbox_token", "company_settings", ["inbox_token"])

    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        _company(),
        sa.Column("customer_id", UUID, sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
        _user("assigned_to"),
        sa.Column("token", sa.String(40), nullable=False, unique=True),
        sa.Column("unread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("last_message_preview", sa.String(200), nullable=False, server_default=""),
        _user("created_by"),
        *_timestamps(),
    )
    op.create_index("ix_conversations_assigned_to", "conversations", ["assigned_to"])
    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        _company(),
        sa.Column("conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _user("author_id"),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("email_message_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "team_channels",
        sa.Column("id", UUID, primary_key=True),
        _company(),
        sa.Column("name", sa.String(60), nullable=False),
        _user("created_by"),
        *_timestamps(),
    )
    op.create_table(
        "team_messages",
        sa.Column("id", UUID, primary_key=True),
        _company(),
        sa.Column("channel_id", UUID, sa.ForeignKey("team_channels.id", ondelete="CASCADE"), nullable=False, index=True),
        _user("author_id"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("team_messages")
    op.drop_table("team_channels")
    op.drop_table("messages")
    op.drop_index("ix_conversations_assigned_to", table_name="conversations")
    op.drop_table("conversations")
    op.drop_constraint("uq_company_settings_inbox_token", "company_settings", type_="unique")
    op.drop_column("company_settings", "inbox_token")
