"""custom fields and customer/client wording

Revision ID: e5b8f2c41a93
Revises: c92e4d1a7b60
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e5b8f2c41a93"
down_revision = "c92e4d1a7b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity", sa.String(20), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("options", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("entity", "key", name="uq_custom_fields_entity_key"),
    )
    op.create_index("ix_custom_fields_entity", "custom_fields", ["entity"])
    for table in ("customers", "deals"):
        op.add_column(
            table,
            sa.Column("custom_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
    op.add_column(
        "company_settings",
        sa.Column("customer_term", sa.String(20), nullable=False, server_default="customer"),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "customer_term")
    for table in ("customers", "deals"):
        op.drop_column(table, "custom_fields")
    op.drop_index("ix_custom_fields_entity", table_name="custom_fields")
    op.drop_table("custom_fields")
