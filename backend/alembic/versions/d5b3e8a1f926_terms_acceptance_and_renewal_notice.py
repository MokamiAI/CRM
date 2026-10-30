"""terms acceptance on each account, and the yearly renewal notice

ECTA s11/s22 and good evidence: when each person agreed to the terms and
privacy policy, and which version. CPA s14(2)(c): a fixed-term (yearly)
plan's holder is told 40 to 80 business days before it renews; this records
the period end each notice was sent for, so it goes once a year.

Revision ID: d5b3e8a1f926
Revises: c2f9a7d4e815
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "d5b3e8a1f926"
down_revision = "c2f9a7d4e815"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("terms_version", sa.String(20), nullable=True))
    op.add_column("subscriptions", sa.Column("renewal_notice_for", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "renewal_notice_for")
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
