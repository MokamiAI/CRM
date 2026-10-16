"""deal priority

Revision ID: b7d41e2c9a10
Revises: 98d52a5f757d
Create Date: 2026-10-16 10:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7d41e2c9a10"
down_revision: Union[str, None] = "98d52a5f757d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing deals become Medium; the database only accepts the three levels.
    op.add_column("deals", sa.Column("priority", sa.String(length=10), server_default="medium", nullable=False))
    op.create_check_constraint("ck_deals_priority", "deals", "priority IN ('high', 'medium', 'low')")


def downgrade() -> None:
    op.drop_constraint("ck_deals_priority", "deals", type_="check")
    op.drop_column("deals", "priority")
