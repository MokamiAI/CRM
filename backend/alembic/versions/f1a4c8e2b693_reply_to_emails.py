"""where clients' replies go: up to 3 addresses per company (empty: the
sender email)

Revision ID: f1a4c8e2b693
Revises: e3c7a9b1d452
Create Date: 2026-11-05 12:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a4c8e2b693"
down_revision: Union[str, None] = "e3c7a9b1d452"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("reply_to_emails", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("company_settings", "reply_to_emails")
