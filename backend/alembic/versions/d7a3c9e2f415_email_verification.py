"""Email verification: users.email_verified_at

Revision ID: d7a3c9e2f415
Revises: c5f2e8a1d937
Create Date: 2026-10-11 18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3c9e2f415"
down_revision: Union[str, None] = "c5f2e8a1d937"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # People who signed up before verification existed aren't asked again.
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
