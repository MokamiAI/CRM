"""multi-tenancy: company_id on every tenant-owned table

Each company_settings row is a tenant ("company"). Existing data all
belongs to the one company that existed before this migration.

Revision ID: a8d2e6f19c37
Revises: f7a3c9e2d814
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a8d2e6f19c37"
down_revision = "f7a3c9e2d814"
branch_labels = None
depends_on = None

TABLES = (
    "users",
    "customers",
    "contacts",
    "deals",
    "activities",
    "notes",
    "custom_fields",
    "products",
    "quotes",
    "quote_items",
    "invoices",
    "invoice_items",
    "payments",
    "reminder_logs",
    "segments",
    "campaigns",
    "campaign_recipients",
)


def upgrade() -> None:
    conn = op.get_bind()
    company_id = conn.execute(sa.text("SELECT id FROM company_settings ORDER BY created_at LIMIT 1")).scalar()
    has_rows = any(conn.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {t})")).scalar() for t in TABLES)
    if company_id is None and has_rows:
        company_id = conn.execute(
            sa.text(
                "INSERT INTO company_settings (id, company_name, default_currency, default_timezone, invoice_prefix,"
                " quote_prefix, next_invoice_number, next_quote_number, payment_terms_days, smtp_use_tls,"
                " reminders_enabled, reminder_offsets, customer_term, created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'My Company', 'ZAR', 'Africa/Johannesburg', 'INV-', 'QUO-', 1, 1, 30,"
                " true, true, '{-3,0,7,14}', 'customer', now(), now()) RETURNING id"
            )
        ).scalar()

    for table in TABLES:
        op.add_column(table, sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
        if company_id is not None:
            conn.execute(sa.text(f"UPDATE {table} SET company_id = :c"), {"c": company_id})
        op.alter_column(table, "company_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_company_id", table, "company_settings", ["company_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])

    # Numbers and SKUs are unique within a company, not across companies.
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_unique_constraint("uq_invoices_company_number", "invoices", ["company_id", "invoice_number"])

    op.drop_index("ix_quotes_quote_number", table_name="quotes")
    op.create_index("ix_quotes_quote_number", "quotes", ["quote_number"])
    op.create_unique_constraint("uq_quotes_company_number", "quotes", ["company_id", "quote_number"])

    op.drop_constraint("uq_products_sku", "products", type_="unique")
    op.create_unique_constraint("uq_products_company_sku", "products", ["company_id", "sku"])

    op.drop_constraint("uq_custom_fields_entity_key", "custom_fields", type_="unique")
    op.create_unique_constraint(
        "uq_custom_fields_company_entity_key", "custom_fields", ["company_id", "entity", "key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_custom_fields_company_entity_key", "custom_fields", type_="unique")
    op.create_unique_constraint("uq_custom_fields_entity_key", "custom_fields", ["entity", "key"])
    op.drop_constraint("uq_products_company_sku", "products", type_="unique")
    op.create_unique_constraint("uq_products_sku", "products", ["sku"])
    op.drop_constraint("uq_quotes_company_number", "quotes", type_="unique")
    op.drop_index("ix_quotes_quote_number", table_name="quotes")
    op.create_index("ix_quotes_quote_number", "quotes", ["quote_number"], unique=True)
    op.drop_constraint("uq_invoices_company_number", "invoices", type_="unique")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=True)
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_company_id", table_name=table)
        op.drop_constraint(f"fk_{table}_company_id", table, type_="foreignkey")
        op.drop_column(table, "company_id")
