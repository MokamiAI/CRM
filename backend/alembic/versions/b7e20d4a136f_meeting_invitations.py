"""Meeting invitations and proposed time holds.

Revision ID: b7e20d4a136f
Revises: a9d41c7e2f60
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e20d4a136f"
down_revision = "a9d41c7e2f60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("meetings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("activity_id", sa.UUID(), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("organizer_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("attendee_name", sa.String(241), nullable=False),
        sa.Column("attendee_email", sa.String(255), nullable=False, index=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("location", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_reason", sa.Text()),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("proposed_start", sa.DateTime(timezone=True), index=True),
        sa.Column("proposed_end", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("ends_at > starts_at", name="ck_meeting_duration"),
        sa.CheckConstraint("status IN ('invited','accepted','declined','proposed','cancelled')", name="ck_meeting_status"),
    )


def downgrade():
    op.drop_table("meetings")
