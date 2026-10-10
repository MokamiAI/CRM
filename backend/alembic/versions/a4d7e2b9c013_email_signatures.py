"""email signatures: one per person, one per company

Revision ID: a4d7e2b9c013
Revises: f3c8a1d5e927
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "a4d7e2b9c013"
down_revision = "f3c8a1d5e927"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_signature", sa.Text(), nullable=True))
    op.add_column("company_settings", sa.Column("email_signature", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("company_settings", "email_signature")
    op.drop_column("users", "email_signature")
