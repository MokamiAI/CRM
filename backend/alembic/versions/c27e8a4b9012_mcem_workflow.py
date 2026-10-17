"""Opt-in MCEM milestones, evidence, customer journeys and history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "c27e8a4b9012"
down_revision = "b19a7c4e6210"
branch_labels = None
depends_on = None


def base():
    return [sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
            sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def user(name):
    return sa.Column(name, pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def deal():
    return sa.Column("deal_id", pg.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)


def upgrade():
    op.add_column("deals", sa.Column("mcem_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("deals", sa.Column("parent_deal_id", pg.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_deals_parent_deal_id", "deals", ["parent_deal_id"])
    op.create_table("mcem_journeys", *base(), deal(),
        sa.Column("state", sa.String(12), nullable=False),
        *[sa.Column(k, sa.Text(), nullable=False) for k in ["qualification_reason", "decision_process", "assumptions", "scope", "commitments", "dependencies", "risks", "success_measure"]],
        *[sa.Column(k, sa.Numeric(18, 4), nullable=True) for k in ["baseline", "target", "actual"]],
        sa.Column("unit", sa.String(80), nullable=False), user("delivery_owner_id"), user("account_owner_id"),
        sa.Column("next_review_date", sa.Date(), nullable=True), sa.Column("recurring", sa.Boolean(), nullable=False), sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("deal_id"), sa.CheckConstraint("state IN ('draft', 'active', 'paused')"))
    op.create_table("mcem_milestones", *base(), deal(), sa.Column("key", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("summary", sa.Text(), nullable=False), user("owner_id"),
        sa.Column("due_date", sa.Date(), nullable=True), sa.Column("confirmed_on", sa.Date(), nullable=True), user("confirmed_by"), sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("deal_id", "key"), sa.CheckConstraint("status IN ('not_started', 'in_progress', 'confirmed')"))
    op.create_table("mcem_evidence", *base(),
        sa.Column("milestone_id", pg.UUID(as_uuid=True), sa.ForeignKey("mcem_milestones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("ref_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True), sa.Column("source_label", sa.String(255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False), sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True), user("added_by"))
    event_base = [column for column in base() if column.name != "updated_at"]
    op.create_table("mcem_events", *event_base, deal(), user("actor_id"), sa.Column("kind", sa.String(40), nullable=False), sa.Column("detail", pg.JSONB(), nullable=False))
    for table in ["mcem_journeys", "mcem_milestones", "mcem_evidence", "mcem_events"]:
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])
    for table in ["mcem_milestones", "mcem_events"]:
        op.create_index(f"ix_{table}_deal_id", table, ["deal_id"])
    op.create_index("ix_mcem_evidence_milestone_id", "mcem_evidence", ["milestone_id"])


def downgrade():
    for table in ["mcem_events", "mcem_evidence", "mcem_milestones", "mcem_journeys"]:
        op.drop_table(table)
    op.drop_index("ix_deals_parent_deal_id", table_name="deals")
    op.drop_column("deals", "parent_deal_id")
    op.drop_column("deals", "mcem_enabled")
