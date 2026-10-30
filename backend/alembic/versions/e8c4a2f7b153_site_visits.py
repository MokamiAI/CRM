"""site_visits: visits to the public website, counted without cookies

Each row is one page view or check-up step, with a daily-salted visitor
hash instead of the address. Read by the admin site's Website visitors
page and the nightly report email.

Revision ID: e8c4a2f7b153
Revises: d5b3e8a1f926
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e8c4a2f7b153"
down_revision = "d5b3e8a1f926"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("visitor", sa.String(16), nullable=False),
    )
    op.create_index("ix_site_visits_day", "site_visits", ["day"])
    op.create_index("ix_site_visits_day_visitor", "site_visits", ["day", "visitor"])


def downgrade() -> None:
    op.drop_index("ix_site_visits_day_visitor", table_name="site_visits")
    op.drop_index("ix_site_visits_day", table_name="site_visits")
    op.drop_table("site_visits")
