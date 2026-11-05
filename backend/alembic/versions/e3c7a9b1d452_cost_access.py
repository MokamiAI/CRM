"""costs and bills by permission: one account owner per company, and a
none | view | manage setting per person, set by the owner

Each company's owner is its earliest active admin (normally the person who
signed it up). Until the owner allows others, only the owner sees costs.

Revision ID: e3c7a9b1d452
Revises: d8b1e5f3a720
Create Date: 2026-11-05 08:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e3c7a9b1d452"
down_revision: Union[str, None] = "d8b1e5f3a720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_account_owner", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("cost_access", sa.String(10), nullable=False, server_default="none"))
    op.create_check_constraint("ck_users_cost_access", "users", "cost_access IN ('none', 'view', 'manage')")
    op.execute(
        """
        UPDATE users SET is_account_owner = true
        WHERE id IN (
            SELECT DISTINCT ON (company_id) id FROM users
            WHERE role = 'admin' AND is_active
            ORDER BY company_id, created_at, id
        )
        """
    )
    op.create_index("uq_users_account_owner", "users", ["company_id"], unique=True, postgresql_where=sa.text("is_account_owner"))


def downgrade() -> None:
    op.drop_index("uq_users_account_owner", table_name="users")
    op.drop_constraint("ck_users_cost_access", "users", type_="check")
    op.drop_column("users", "cost_access")
    op.drop_column("users", "is_account_owner")
