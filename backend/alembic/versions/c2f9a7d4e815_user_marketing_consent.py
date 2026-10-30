"""users: whether each person agreed to YGT's own marketing

POPIA s69: YGT may market to the people who use it only once they've said
yes. Ticked (or not) at sign-up, or answered once in the app; changeable
in Settings. None: not asked yet.

Revision ID: c2f9a7d4e815
Revises: b8d4e1f7c302
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "c2f9a7d4e815"
down_revision = "b8d4e1f7c302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("marketing_opt_in", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("marketing_opt_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("marketing_opt_in_source", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "marketing_opt_in_source")
    op.drop_column("users", "marketing_opt_in_at")
    op.drop_column("users", "marketing_opt_in")
