import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vehicle_price_estimator.infrastructure.db.base import Base


class VehicleCanonicalModel(Base):
    __tablename__ = "vehicle_canonical"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_std: Mapped[str] = mapped_column(String(120), nullable=False)
    model_std: Mapped[str] = mapped_column(String(120), nullable=False)
    version_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trim_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    body_type_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fuel_type_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transmission_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engine_displacement_std: Mapped[str | None] = mapped_column(String(20), nullable=True)
    engine_cc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hybrid_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mhev_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    variant_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_tokens_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ListingModel(Base):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_core_listings_brand_model_year", "brand_std", "model_std", "year"),
        Index("ix_core_listings_price_cop", "price_cop"),
        Index("ix_core_listings_mileage_km", "mileage_km"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    vehicle_canonical_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.vehicle_canonical.id"),
        nullable=True,
    )
    listing_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    title_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    price_cop: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    city_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipality_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locality_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipality_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    brand_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trim_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_km: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    fuel_type_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transmission_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engine_displacement_std: Mapped[str | None] = mapped_column(String(20), nullable=True)
    engine_cc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hybrid_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mhev_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    variant_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_tokens_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    vehicle_type_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    color_std: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    outlier_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_last_payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw.listing_payloads.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
