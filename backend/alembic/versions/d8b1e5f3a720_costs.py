"""costs: the bills and expenses a company pays, one-off or recurring

Revision ID: d8b1e5f3a720
Revises: c6f2a9e4b031
Create Date: 2026-11-04 09:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d8b1e5f3a720"
down_revision: Union[str, None] = "c6f2a9e4b031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _common() -> list:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("company_settings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "recurring_costs",
        *_common(),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("next_run_date", sa.Date, nullable=False, index=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "costs",
        *_common(),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("category", sa.String(60), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False, index=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="due"),
        sa.Column("paid_date", sa.Date, nullable=True, index=True),
        sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("purchase_order_id", UUID, sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recurring_cost_id", UUID, sa.ForeignKey("recurring_costs.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("recurrence_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("receipt_name", sa.String(255), nullable=True),
        sa.Column("receipt_type", sa.String(120), nullable=True),
        sa.Column("receipt_size", sa.Integer, nullable=True),
        sa.Column("receipt_data", sa.LargeBinary, nullable=True),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("status IN ('due', 'paid')", name="ck_costs_status"),
        sa.CheckConstraint("amount > 0", name="ck_costs_amount_positive"),
        sa.UniqueConstraint("recurring_cost_id", "recurrence_date", name="uq_costs_recurrence"),
        sa.UniqueConstraint("purchase_order_id", name="uq_costs_purchase_order"),
    )


def downgrade() -> None:
    op.drop_table("costs")
    op.drop_table("recurring_costs")
