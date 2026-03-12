from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.listing_feature import ListingFeatureModel
from vehicle_price_estimator.infrastructure.db.models.vehicle import ListingModel
from vehicle_price_estimator.infrastructure.db.session import SessionLocal
from vehicle_price_estimator.pipelines.processing.staging_to_core import (
    _compute_equipment_score,
    _compute_vehicle_age_bucket,
)


LOGGER = get_logger(__name__)
CURRENT_YEAR = datetime.now(UTC).year


def backfill_core_listing_features() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    with SessionLocal() as db:
        listings = db.query(ListingModel).all()
        existing_features = {
            feature.listing_id: feature
            for feature in db.query(ListingFeatureModel).all()
        }

        updated = 0
        for listing in listings:
            feature = existing_features.get(listing.id)
            if feature is None:
                snapshot_date = (
                    listing.last_seen_at.date()
                    if listing.last_seen_at is not None
                    else datetime.now(UTC).date()
                )
                feature = ListingFeatureModel(listing_id=listing.id, snapshot_date=snapshot_date)
                db.add(feature)
                existing_features[listing.id] = feature

            vehicle_age = None
            vehicle_age_bucket = None
            technomechanical_required_flag = False
            years_since_technomechanical_threshold = None
            km_per_year = feature.km_per_year

            if listing.year is not None:
                vehicle_age = Decimal(max(CURRENT_YEAR - listing.year, 0))
                vehicle_age_bucket = _compute_vehicle_age_bucket(vehicle_age)
                technomechanical_required_flag = vehicle_age >= Decimal("5")
                years_since_technomechanical_threshold = max(vehicle_age - Decimal("5"), Decimal("0")).quantize(
                    Decimal("0.00")
                )
                if listing.mileage_km is not None and vehicle_age > 0:
                    km_per_year = (listing.mileage_km / vehicle_age).quantize(Decimal("0.01"))

            feature.vehicle_age = vehicle_age
            feature.vehicle_age_bucket = vehicle_age_bucket
            feature.technomechanical_required_flag = technomechanical_required_flag
            feature.years_since_technomechanical_threshold = years_since_technomechanical_threshold
            feature.km_per_year = km_per_year

            if listing.first_seen_at is not None and listing.last_seen_at is not None:
                feature.listing_age_days = Decimal(
                    max((listing.last_seen_at.date() - listing.first_seen_at.date()).days, 0)
                ).quantize(Decimal("0.00"))

            if listing.title_clean or listing.version_std:
                feature.equipment_score = _compute_equipment_score(
                    listing.title_clean,
                    listing.version_std,
                ).quantize(Decimal("0.0001"))

            updated += 1

        db.commit()

    LOGGER.info("Backfill de core.listing_features completado para %s listings.", updated)
