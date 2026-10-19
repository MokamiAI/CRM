"""Allow unpaid subscription invoices when a trial expires."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "e50b7d9f2135"
down_revision = "d49a6c8e1024"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("subscription_invoices", "payment_id", existing_type=UUID(), nullable=True)
    op.add_column("subscription_invoices", sa.Column("trial_subscription_id", UUID(), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True))
    op.create_unique_constraint("uq_subscription_invoice_trial", "subscription_invoices", ["trial_subscription_id"])
    op.add_column("subscription_invoices", sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("subscription_invoices", "emailed_at")
    op.drop_constraint("uq_subscription_invoice_trial", "subscription_invoices", type_="unique")
    op.drop_column("subscription_invoices", "trial_subscription_id")
    # Refuse to discard unpaid invoice records on rollback.
    op.alter_column("subscription_invoices", "payment_id", existing_type=UUID(), nullable=False)
