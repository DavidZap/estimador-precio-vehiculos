from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.session import SessionLocal


NUMERIC_FEATURES = [
    "year",
    "mileage_km",
    "engine_cc",
    "vehicle_age",
    "km_per_year",
    "equipment_score",
    "version_rarity_score",
    "regional_market_score",
    "listing_age_days",
    "comparable_inventory_density",
    "hybrid_flag",
    "mhev_flag",
]

CATEGORICAL_FEATURES = [
    "brand_std",
    "model_std",
    "trim_std",
    "engine_displacement_std",
    "transmission_std",
    "fuel_type_std",
    "vehicle_type_std",
    "department_std",
    "municipality_std",
    "locality_std",
    "color_std",
]

TARGET_COLUMN = "price_cop"
IDENTIFIER_COLUMNS = ["listing_id", "source_listing_id", "source_name", "first_seen_at", "updated_at"]


@dataclass(slots=True)
class TrainingDataset:
    dataset_id: uuid.UUID
    dataframe: pd.DataFrame
    dataset_path: Path
    metadata_path: Path
    feature_schema: dict
    created_at: datetime


def build_training_dataset(
    *,
    min_year: int = 2010,
    exclude_outliers: bool = True,
    active_only: bool = True,
) -> TrainingDataset:
    settings = get_settings()
    dataset_id = uuid.uuid4()
    created_at = datetime.now(UTC)
    artifacts_root = settings.artifacts_path / "training"
    datasets_root = artifacts_root / "datasets"
    datasets_root.mkdir(parents=True, exist_ok=True)

    where_clauses = [
        "l.price_cop is not null",
        "l.year is not null",
        "l.year >= :min_year",
        "l.brand_std is not null",
        "l.model_std is not null",
    ]
    if exclude_outliers:
        where_clauses.append("coalesce(l.outlier_flag, false) = false")
    if active_only:
        where_clauses.append("coalesce(l.is_active, true) = true")

    query = text(
        f"""
        select
            l.id as listing_id,
            l.source_listing_id,
            l.source_name,
            l.price_cop,
            l.year,
            l.mileage_km,
            l.brand_std,
            l.model_std,
            l.trim_std,
            l.engine_displacement_std,
            l.engine_cc,
            l.transmission_std,
            l.fuel_type_std,
            l.vehicle_type_std,
            l.department_std,
            l.municipality_std,
            l.locality_std,
            l.color_std,
            cast(l.hybrid_flag as integer) as hybrid_flag,
            cast(l.mhev_flag as integer) as mhev_flag,
            l.first_seen_at,
            l.updated_at,
            f.vehicle_age,
            f.km_per_year,
            f.equipment_score,
            f.version_rarity_score,
            f.regional_market_score,
            f.listing_age_days,
            f.comparable_inventory_density
        from core.listings l
        left join core.listing_features f
            on f.listing_id = l.id
        where {" and ".join(where_clauses)}
        order by l.first_seen_at asc, l.updated_at asc
        """
    )

    with SessionLocal() as db:
        rows = db.execute(query, {"min_year": min_year}).mappings().all()

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        raise ValueError("No hay datos suficientes para construir el dataset de entrenamiento.")

    for column in NUMERIC_FEATURES + [TARGET_COLUMN]:
        if column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataset_path = datasets_root / f"{dataset_id}.parquet"
    metadata_path = datasets_root / f"{dataset_id}.metadata.json"
    dataframe.to_parquet(dataset_path, index=False)

    feature_schema = {
        "dataset_id": str(dataset_id),
        "target_column": TARGET_COLUMN,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "identifier_columns": IDENTIFIER_COLUMNS,
        "row_count": int(len(dataframe)),
        "min_year": min_year,
        "exclude_outliers": exclude_outliers,
        "active_only": active_only,
        "created_at": created_at.isoformat(),
    }
    metadata_path.write_text(
        json.dumps(feature_schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return TrainingDataset(
        dataset_id=dataset_id,
        dataframe=dataframe,
        dataset_path=dataset_path,
        metadata_path=metadata_path,
        feature_schema=feature_schema,
        created_at=created_at,
    )
