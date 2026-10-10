"""CRM core: contacts, deals pipeline, activities, notes; quotes.deal_id

Revision ID: a41f6c2d8e15
Revises: 7c3e1a9b2f40
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a41f6c2d8e15"
down_revision = "7c3e1a9b2f40"
branch_labels = None
depends_on = None

DEAL_STAGES = ("lead", "qualified", "proposal", "negotiation", "won", "lost")
ACTIVITY_TYPES = ("call", "meeting", "task", "email", "deadline")


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _user_fk(name):
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    deal_stage = postgresql.ENUM(*DEAL_STAGES, name="deal_stage", create_type=False)
    activity_type = postgresql.ENUM(*ACTIVITY_TYPES, name="activity_type", create_type=False)
    deal_stage.create(op.get_bind(), checkfirst=True)
    activity_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("job_title", sa.String(120), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_index("ix_contacts_customer_id", "contacts", ["customer_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])

    op.create_table(
        "deals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        _user_fk("owner_id"),
        sa.Column("stage", deal_stage, nullable=False, server_default="lead"),
        sa.Column("value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.String(255), nullable=True),
        _user_fk("created_by"),
        *_timestamps(),
    )
    op.create_index("ix_deals_customer_id", "deals", ["customer_id"])
    op.create_index("ix_deals_owner_id", "deals", ["owner_id"])
    op.create_index("ix_deals_stage", "deals", ["stage"])

    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", activity_type, nullable=False, server_default="task"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("due_time", sa.Time(), nullable=True),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        _user_fk("owner_id"),
        _user_fk("created_by"),
        *_timestamps(),
    )
    for column in ("due_date", "done", "customer_id", "deal_id", "owner_id"):
        op.create_index(f"ix_activities_{column}", "activities", [column])

    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="CASCADE"), nullable=True),
        _user_fk("author_id"),
        *_timestamps(),
    )
    op.create_index("ix_notes_customer_id", "notes", ["customer_id"])
    op.create_index("ix_notes_deal_id", "notes", ["deal_id"])

    op.add_column(
        "quotes",
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_quotes_deal_id", "quotes", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_quotes_deal_id", table_name="quotes")
    op.drop_column("quotes", "deal_id")
    op.drop_table("notes")
    op.drop_table("activities")
    op.drop_table("deals")
    op.drop_table("contacts")
    postgresql.ENUM(name="activity_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="deal_stage").drop(op.get_bind(), checkfirst=True)
