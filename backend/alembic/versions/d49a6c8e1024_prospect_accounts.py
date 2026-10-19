"""Distinguish pipeline prospects from customer accounts."""
from alembic import op
import sqlalchemy as sa

revision = "d49a6c8e1024"
down_revision = "c27e8a4b9012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("is_prospect", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_customers_is_prospect", "customers", ["is_prospect"])
    # Accounts with only unwon opportunities and no invoices are prospects.
    # Keep established accounts and all their identifiers/history intact.
    op.execute("""
        UPDATE customers c SET is_prospect = true
        WHERE EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = c.id)
          AND NOT EXISTS (SELECT 1 FROM deals d WHERE d.customer_id = c.id AND d.stage = 'won')
          AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.customer_id = c.id)
    """)


def downgrade():
    op.drop_index("ix_customers_is_prospect", table_name="customers")
    op.drop_column("customers", "is_prospect")
