"""company settings: outgoing email configuration

Revision ID: 1d88b9a5d6c2
Revises: e6489ac0f07a
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = "1d88b9a5d6c2"
down_revision = "e6489ac0f07a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("sender_name", sa.String(255), nullable=True))
    op.add_column("company_settings", sa.Column("sender_email", sa.String(255), nullable=True))
    op.add_column("company_settings", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column("company_settings", sa.Column("smtp_port", sa.Integer(), nullable=True))
    op.add_column("company_settings", sa.Column("smtp_username", sa.String(255), nullable=True))
    op.add_column("company_settings", sa.Column("smtp_password", sa.String(255), nullable=True))
    op.add_column(
        "company_settings",
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "smtp_use_tls")
    op.drop_column("company_settings", "smtp_password")
    op.drop_column("company_settings", "smtp_username")
    op.drop_column("company_settings", "smtp_port")
    op.drop_column("company_settings", "smtp_host")
    op.drop_column("company_settings", "sender_email")
    op.drop_column("company_settings", "sender_name")
