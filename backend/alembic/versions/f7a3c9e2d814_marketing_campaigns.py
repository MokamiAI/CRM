"""marketing: campaigns, recipients, audiences, opt-out, product specials

Revision ID: f7a3c9e2d814
Revises: e5b8f2c41a93
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f7a3c9e2d814"
down_revision = "e5b8f2c41a93"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        *_timestamps(),
    )
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("preheader", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("product_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("cta_text", sa.String(60), nullable=True),
        sa.Column("cta_url", sa.String(500), nullable=True),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("segments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_table(
        "campaign_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_campaign_recipients_campaign_id", "campaign_recipients", ["campaign_id"])
    op.create_index("ix_campaign_recipients_customer_id", "campaign_recipients", ["customer_id"])

    op.add_column("customers", sa.Column("marketing_opt_out", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("customers", sa.Column("marketing_opt_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.String(500), nullable=True))
    op.add_column("products", sa.Column("special_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("products", sa.Column("special_until", sa.Date(), nullable=True))


def downgrade() -> None:
    for column in ("special_until", "special_price", "image_url"):
        op.drop_column("products", column)
    op.drop_column("customers", "marketing_opt_out_at")
    op.drop_column("customers", "marketing_opt_out")
    op.drop_table("campaign_recipients")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_table("segments")
