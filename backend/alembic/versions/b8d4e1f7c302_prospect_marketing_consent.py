"""prospects: marketing consent and the one-time invite

POPIA s69: a prospect may only get marketing once they've agreed to it,
and may be approached once to ask. These record the agreement (when and
how), the one invite, and the private code their reply link carries.

Revision ID: b8d4e1f7c302
Revises: e6b13f8a4c21
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d4e1f7c302"
down_revision = "e6b13f8a4c21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("marketing_consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("marketing_consent_source", sa.String(200), nullable=True))
    op.add_column("customers", sa.Column("consent_invited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("consent_token", sa.String(64), nullable=True))
    op.create_index("ix_customers_consent_token", "customers", ["consent_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_customers_consent_token", table_name="customers")
    op.drop_column("customers", "consent_token")
    op.drop_column("customers", "consent_invited_at")
    op.drop_column("customers", "marketing_consent_source")
    op.drop_column("customers", "marketing_consent_at")
