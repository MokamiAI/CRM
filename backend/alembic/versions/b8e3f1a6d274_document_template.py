"""document template: how a company's invoices, quotes and statements look

Revision ID: b8e3f1a6d274
Revises: a4d7e2b9c013
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b8e3f1a6d274"
down_revision = "a4d7e2b9c013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("document_template", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("company_settings", "document_template")
