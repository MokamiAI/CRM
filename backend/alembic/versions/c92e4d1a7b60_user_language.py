"""users: per-user UI language

Revision ID: c92e4d1a7b60
Revises: a41f6c2d8e15
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa

revision = "c92e4d1a7b60"
down_revision = "a41f6c2d8e15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(8), nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("users", "language")
