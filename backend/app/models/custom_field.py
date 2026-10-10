from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

# Records that can carry custom fields, and the kinds of value a field holds.
CUSTOM_FIELD_ENTITIES = ("customer", "deal")
CUSTOM_FIELD_TYPES = ("text", "number", "date", "select", "boolean")


class CustomFieldDefinition(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """An admin-defined extra field. Values live in the owning record's
    `custom_fields` JSONB column, keyed by `key` (stable even if the label
    is renamed later)."""

    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("company_id", "entity", "key", name="uq_custom_fields_company_entity_key"),)

    entity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Choices for "select" fields; empty for every other type.
    options: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
