from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class CompanySettings(UUIDPKMixin, TimestampMixin, Base):
    """Singleton-style table: the application expects exactly one row."""

    __tablename__ = "company_settings"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ZAR")
    default_timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Africa/Johannesburg"
    )
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invoice_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="INV-")
    quote_prefix: Mapped[str] = mapped_column(String(20), nullable=False, default="QUO-")
    next_invoice_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_quote_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
