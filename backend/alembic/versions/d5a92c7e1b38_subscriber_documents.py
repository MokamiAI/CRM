"""Subscribers' quote, trial invoice, recurring invoice and seat count in YGT's pipeline.

Revision ID: d5a92c7e1b38
Revises: c3f81a5d92e4
"""
from alembic import op
import sqlalchemy as sa

revision = "d5a92c7e1b38"
down_revision = "c3f81a5d92e4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriber_links", sa.Column("quote_id", sa.UUID(), sa.ForeignKey("quotes.id", ondelete="SET NULL")))
    op.add_column("subscriber_links", sa.Column("trial_invoice_id", sa.UUID(), sa.ForeignKey("invoices.id", ondelete="SET NULL")))
    op.add_column("subscriber_links", sa.Column("recurring_id", sa.UUID(), sa.ForeignKey("recurring_invoices.id", ondelete="SET NULL")))
    op.add_column("subscriber_links", sa.Column("seats", sa.Integer()))


def downgrade():
    for column in ("seats", "recurring_id", "trial_invoice_id", "quote_id"):
        op.drop_column("subscriber_links", column)
