"""company_settings.country, tax_name and default_tax_rate

Where the company trades (fills its currency, tax, dialling code and time
zone), what its tax is called on documents, and the rate new lines start
at. Every existing company is South African: ZA, VAT, 15%.

Revision ID: d5e1a8c3f927
Revises: c4d9e2a7f816
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e1a8c3f927"
down_revision = "c4d9e2a7f816"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("country", sa.String(2), nullable=False, server_default="ZA"))
    op.add_column("company_settings", sa.Column("tax_name", sa.String(20), nullable=False, server_default="VAT"))
    op.add_column("company_settings", sa.Column("default_tax_rate", sa.Numeric(5, 2), nullable=False, server_default="15"))


def downgrade() -> None:
    op.drop_column("company_settings", "default_tax_rate")
    op.drop_column("company_settings", "tax_name")
    op.drop_column("company_settings", "country")
