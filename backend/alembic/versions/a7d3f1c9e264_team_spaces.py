"""team spaces: private channels with members, replies, edits, files,
reactions, and each person's chat colour

Revision ID: a7d3f1c9e264
Revises: e8c4a2f7b153
Create Date: 2026-10-31 20:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7d3f1c9e264"
down_revision: Union[str, None] = "e8c4a2f7b153"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Channels made before spaces stay open to the whole team.
    op.add_column("team_channels", sa.Column("is_private", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("team_messages", sa.Column("reply_to_id", sa.UUID(), nullable=True))
    op.add_column("team_messages", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_team_messages_reply_to", "team_messages", "team_messages", ["reply_to_id"], ["id"], ondelete="SET NULL")
    op.add_column("users", sa.Column("chat_color", sa.String(length=20), nullable=True))

    op.create_table(
        "team_channel_members",
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["team_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company_settings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "user_id", name="uq_team_channel_member"),
    )
    op.create_index("ix_team_channel_members_channel_id", "team_channel_members", ["channel_id"])
    op.create_index("ix_team_channel_members_user_id", "team_channel_members", ["user_id"])
    op.create_index("ix_team_channel_members_company_id", "team_channel_members", ["company_id"])

    op.create_table(
        "team_message_attachments",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["team_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company_settings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_message_attachments_message_id", "team_message_attachments", ["message_id"])
    op.create_index("ix_team_message_attachments_company_id", "team_message_attachments", ["company_id"])

    op.create_table(
        "team_message_reactions",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["team_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company_settings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_team_message_reaction"),
    )
    op.create_index("ix_team_message_reactions_message_id", "team_message_reactions", ["message_id"])
    op.create_index("ix_team_message_reactions_company_id", "team_message_reactions", ["company_id"])


def downgrade() -> None:
    op.drop_table("team_message_reactions")
    op.drop_table("team_message_attachments")
    op.drop_table("team_channel_members")
    op.drop_column("users", "chat_color")
    op.drop_constraint("fk_team_messages_reply_to", "team_messages", type_="foreignkey")
    op.drop_column("team_messages", "edited_at")
    op.drop_column("team_messages", "reply_to_id")
    op.drop_column("team_channels", "is_private")
