"""one invoice per quote: accepted quotes become a single draft invoice

Revision ID: e4b7c2d9a813
Revises: 0a243a6bd57b
Create Date: 2026-10-14 08:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e4b7c2d9a813'
down_revision: Union[str, None] = '0a243a6bd57b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'uq_invoices_quote_id', 'invoices', ['quote_id'], unique=True,
        postgresql_where=sa.text('quote_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_invoices_quote_id', table_name='invoices', postgresql_where=sa.text('quote_id IS NOT NULL'))
