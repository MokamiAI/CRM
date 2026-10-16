"""user invitations: invited, accepted

Revision ID: d5a2c7e9f013
Revises: c3e8f1a2b4d6
Create Date: 2026-10-16 15:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5a2c7e9f013"
down_revision: Union[str, None] = "c3e8f1a2b4d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("invite_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "invite_accepted_at")
    op.drop_column("users", "invited_at")
