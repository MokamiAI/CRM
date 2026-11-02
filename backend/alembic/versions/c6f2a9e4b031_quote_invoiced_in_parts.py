"""a quote can be invoiced in parts (deposit, stages, balance): several
invoices per quote. Double conversion stays impossible: the quote row is
locked while it's invoiced, and a converted quote can't be converted again.

Revision ID: c6f2a9e4b031
Revises: b4e8c2a6d917
Create Date: 2026-11-01 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c6f2a9e4b031"
down_revision: Union[str, None] = "b4e8c2a6d917"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_invoices_quote_id", table_name="invoices", postgresql_where=sa.text("quote_id IS NOT NULL"))
    op.create_index("ix_invoices_quote_id", "invoices", ["quote_id"])


def downgrade() -> None:
    op.drop_index("ix_invoices_quote_id", table_name="invoices")
    op.create_index("uq_invoices_quote_id", "invoices", ["quote_id"], unique=True, postgresql_where=sa.text("quote_id IS NOT NULL"))
