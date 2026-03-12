import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vehicle_price_estimator.infrastructure.db.base import Base


class ListingFeatureModel(Base):
    __tablename__ = "listing_features"
    __table_args__ = {"schema": "core"}

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.listings.id"),
        primary_key=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    vehicle_age: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    vehicle_age_bucket: Mapped[str | None] = mapped_column(String(40), nullable=True)
    technomechanical_required_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    years_since_technomechanical_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )
    km_per_year: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    equipment_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    version_rarity_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    regional_market_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    listing_age_days: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    comparable_inventory_density: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    title_embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text_flags_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feature_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
