"""onboarding: guided tour per user, dismissible checklist per company

Revision ID: e8b4c2f7a196
Revises: d2a9f4c6b815
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = "e8b4c2f7a196"
down_revision = "d2a9f4c6b815"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tour_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("company_settings", sa.Column("onboarding_dismissed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("company_settings", "onboarding_dismissed_at")
    op.drop_column("users", "tour_completed_at")
