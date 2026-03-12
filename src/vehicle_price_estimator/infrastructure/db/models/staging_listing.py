from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vehicle_price_estimator.infrastructure.db.base import Base


class StagingMarketplaceListingModel(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        Index("ix_staging_marketplace_listings_source_listing_id", "source_listing_id"),
        Index("ix_staging_marketplace_listings_extract_run_id", "extract_run_id"),
        {"schema": "staging"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    extract_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, default="mercadolibre_co")
    source_listing_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    location_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    brand_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year_raw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_raw: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    fuel_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transmission_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vehicle_type_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    color_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attributes_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
