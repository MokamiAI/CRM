"""Discovery (Scale): potential leads YGT finds for a company, waiting for
someone to add them to the pipeline or dismiss them.

Two kinds of source:
  * outside: businesses near the company on OpenStreetMap, of the kinds of
    customers it chose (public, free data; "© OpenStreetMap contributors");
  * its own records: customers who have gone quiet, deals lost a while ago,
    and sent quotes nobody followed up.

`external_ref` is unique per company, so a weekly run never finds the same
lead twice, and a dismissed lead stays dismissed."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import TenantMixin
from app.models.base import TimestampMixin, UUIDPKMixin

# Where a lead came from.
SOURCES = ("osm", "quiet_customer", "lost_deal", "stale_quote")
STATUSES = ("new", "added", "dismissed")


class DiscoverySettings(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    """One row per company: where to look and for what."""

    __tablename__ = "discovery_settings"
    __table_args__ = (UniqueConstraint("company_id", name="uq_discovery_settings_company"),)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    radius_km: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    industries: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The map lookup: "looking" (running now), "done" or "failed" (map busy).
    nearby_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    nearby_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveredLead(TenantMixin, UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "discovered_leads"
    __table_args__ = (UniqueConstraint("company_id", "external_ref", name="uq_discovered_leads_ref"),)

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="new", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "school", from OpenStreetMap
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Why it's worth a call: amounts and dates for the reason line.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_contact: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
