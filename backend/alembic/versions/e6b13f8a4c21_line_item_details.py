"""Line items get a description under the item name (quotes, invoices, purchase orders).

Revision ID: e6b13f8a4c21
Revises: d5a92c7e1b38
"""
from alembic import op
import sqlalchemy as sa

revision = "e6b13f8a4c21"
down_revision = "d5a92c7e1b38"
branch_labels = None
depends_on = None

TABLES = ("quote_items", "invoice_items", "purchase_order_items")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("details", sa.Text()))


def downgrade():
    for table in TABLES:
        op.drop_column(table, "details")
