"""channel connections: each company's own mailbox, WhatsApp and SMS accounts

Also makes conversations multi-channel and encrypts SMTP passwords that
were saved in plain text before credentials were encrypted at rest.

Revision ID: c6e1a4b7d283
Revises: b3f7c1d9e542
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.crypto import encrypt

revision = "c6e1a4b7d283"
down_revision = "b3f7c1d9e542"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secrets", sa.Text(), nullable=True),
        sa.Column("webhook_token", sa.String(48), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="untested"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "kind", name="uq_channel_connections_company_kind"),
    )

    op.add_column("conversations", sa.Column("channel", sa.String(20), nullable=False, server_default="email"))
    op.create_index("ix_conversations_channel", "conversations", ["channel"])
    op.add_column("conversations", sa.Column("contact_phone", sa.String(32), nullable=True))
    op.create_index("ix_conversations_contact_phone", "conversations", ["contact_phone"])
    op.alter_column("conversations", "contact_email", nullable=True)
    op.add_column("messages", sa.Column("external_id", sa.String(255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, smtp_password FROM company_settings WHERE smtp_password IS NOT NULL AND smtp_password <> ''")).all()
    for row_id, password in rows:
        if not password.startswith("gAAAA"):
            conn.execute(sa.text("UPDATE company_settings SET smtp_password = :p WHERE id = :i"), {"p": encrypt(password), "i": row_id})


def downgrade() -> None:
    op.drop_column("messages", "external_id")
    op.alter_column("conversations", "contact_email", nullable=False)
    op.drop_index("ix_conversations_contact_phone", table_name="conversations")
    op.drop_column("conversations", "contact_phone")
    op.drop_index("ix_conversations_channel", table_name="conversations")
    op.drop_column("conversations", "channel")
    op.drop_table("channel_connections")
    # Passwords stay encrypted; the app reads both forms.
