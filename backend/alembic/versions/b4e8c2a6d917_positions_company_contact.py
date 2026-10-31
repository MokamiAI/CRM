"""each person's position; the company's phone and website (signatures);
the week of the sales quote each person has seen

Revision ID: b4e8c2a6d917
Revises: a7d3f1c9e264
Create Date: 2026-10-31 21:00:00+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4e8c2a6d917"
down_revision: Union[str, None] = "a7d3f1c9e264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("job_title", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("quote_seen", sa.String(length=20), nullable=True))
    op.add_column("company_settings", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("company_settings", sa.Column("website", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("company_settings", "website")
    op.drop_column("company_settings", "phone")
    op.drop_column("users", "quote_seen")
    op.drop_column("users", "job_title")
