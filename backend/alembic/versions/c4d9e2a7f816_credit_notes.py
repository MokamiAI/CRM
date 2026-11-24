"""credit_notes: reduce an invoice that has gone out, even after a payment

credit_notes and credit_note_items, invoices.amount_credited, and the
company's CN- numbering.

Revision ID: c4d9e2a7f816
Revises: b2e8f4a6d913
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d9e2a7f816"
down_revision = "b2e8f4a6d913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("amount_credited", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("company_settings", sa.Column("credit_note_prefix", sa.String(20), nullable=False, server_default="CN-"))
    op.add_column("company_settings", sa.Column("next_credit_note_number", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "credit_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credit_note_number", sa.String(50), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="issued"),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "credit_note_number", name="uq_credit_notes_company_number"),
    )
    op.create_index("ix_credit_notes_company_id", "credit_notes", ["company_id"])
    op.create_index("ix_credit_notes_credit_note_number", "credit_notes", ["credit_note_number"])
    op.create_index("ix_credit_notes_invoice_id", "credit_notes", ["invoice_id"])
    op.create_index("ix_credit_notes_customer_id", "credit_notes", ["customer_id"])

    op.create_table(
        "credit_note_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credit_note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_credit_note_items_company_id", "credit_note_items", ["company_id"])
    op.create_index("ix_credit_note_items_credit_note_id", "credit_note_items", ["credit_note_id"])


def downgrade() -> None:
    op.drop_table("credit_note_items")
    op.drop_table("credit_notes")
    op.drop_column("company_settings", "next_credit_note_number")
    op.drop_column("company_settings", "credit_note_prefix")
    op.drop_column("invoices", "amount_credited")
