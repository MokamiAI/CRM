from datetime import date

from sqlalchemy import Boolean, Date, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin


class Product(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("company_id", "sku", name="uq_products_company_sku"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Shown in marketing campaigns: a photo, and an optional promotional price
    # (excl. tax, like unit_price) that runs until special_until inclusive.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    special_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    special_until: Mapped[date | None] = mapped_column(Date, nullable=True)
