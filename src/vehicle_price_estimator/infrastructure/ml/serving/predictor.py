from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, func, select
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.orm import Session

from vehicle_price_estimator.api.schemas.market import ComparableItem
from vehicle_price_estimator.config.logging import get_logger
from vehicle_price_estimator.infrastructure.db.models.model_registry import ModelRegistryModel
from vehicle_price_estimator.infrastructure.db.models.prediction_log import PredictionLogModel
from vehicle_price_estimator.infrastructure.db.models.staging_listing import StagingMarketplaceListingModel
from vehicle_price_estimator.infrastructure.db.models.vehicle import ListingModel
from vehicle_price_estimator.infrastructure.ml.features.feature_schema import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from vehicle_price_estimator.infrastructure.ml.serving.scopes import MAINSTREAM_BRANDS, resolve_registry_scope, resolve_requested_scope
from vehicle_price_estimator.pipelines.processing.staging_to_core import _compute_equipment_score, _compute_vehicle_age_bucket


LOGGER = get_logger(__name__)
CURRENT_YEAR = datetime.now(UTC).year
PREMIUM_BRANDS = {"Audi", "BMW", "Mercedes-Benz", "Lexus", "Volvo", "Jaguar", "Land Rover"}
CATBOOST_FALLBACK_FEATURES = [
    "brand_std",
    "model_std",
    "year",
    "mileage_km",
    "vehicle_age",
    "vehicle_age_bucket",
    "technomechanical_required_flag",
    "years_since_technomechanical_threshold",
    "trim_std",
    "engine_displacement_std",
    "engine_cc",
    "transmission_std",
    "fuel_type_std",
    "municipality_std",
    "department_std",
    "hybrid_flag",
    "mhev_flag",
    "km_per_year",
    "equipment_score",
    "brand_model_inventory_count",
    "brand_model_year_inventory_count",
    "brand_model_municipality_inventory_count",
    "is_premium_brand_flag",
    "vehicle_type_std",
    "locality_std",
]


@dataclass(slots=True)
class PredictionBundle:
    registry_row: ModelRegistryModel
    payload: dict[str, Any]


@lru_cache(maxsize=16)
def _load_artifact(artifact_path: str) -> dict[str, Any]:
    import joblib

    return joblib.load(artifact_path)


@lru_cache(maxsize=32)
def _load_model_sidecar(artifact_path: str) -> dict[str, Any]:
    metadata_path = Path(artifact_path).with_name("metadata.json")
    if not metadata_path.exists():
        return {}
    try:
        import json

        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_scope_candidates(db: Session, scope: str) -> list[ModelRegistryModel]:
    rows = db.query(ModelRegistryModel).order_by(ModelRegistryModel.created_at.desc()).all()
    return [
        row
        for row in rows
        if resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json) == scope
    ]


def _get_serving_row(db: Session, requested_scope: str) -> tuple[ModelRegistryModel | None, str]:
    scope_candidates = _get_scope_candidates(db, requested_scope)
    active = next((row for row in scope_candidates if row.is_active), None)
    if active is not None:
        return active, requested_scope

    if scope_candidates:
        return scope_candidates[0], requested_scope

    if requested_scope != "global":
        global_candidates = _get_scope_candidates(db, "global")
        active_global = next((row for row in global_candidates if row.is_active), None)
        if active_global is not None:
            return active_global, "global"
        if global_candidates:
            return global_candidates[0], "global"

    return None, requested_scope


def get_active_serving_models(db: Session) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    rows = db.query(ModelRegistryModel).order_by(ModelRegistryModel.created_at.desc()).all()
    seen_scopes: set[str] = set()
    for row in rows:
        scope = resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json)
        if scope in seen_scopes:
            continue
        if not row.is_active:
            continue
        seen_scopes.add(scope)
        sidecar = _load_model_sidecar(row.artifact_path)
        payload.append(
            {
                "registry_id": str(row.id),
                "model_name": row.model_name,
                "model_version": row.model_version,
                "algorithm": row.algorithm,
                "model_scope": scope,
                "status": row.status,
                "is_active": row.is_active,
                "promoted_at": row.promoted_at,
                "metrics": row.metrics_json or {},
                "scope_filters": row.scope_filters_json or (row.feature_schema_json or {}),
                "selected_features": row.selected_features_json or sidecar.get("selected_feature_names", []),
                "shap_summary": row.shap_summary_json or sidecar.get("shap_summary"),
            }
        )
    return payload


def _resolve_selected_features(registry_row: ModelRegistryModel) -> list[str]:
    if registry_row.selected_features_json:
        return list(registry_row.selected_features_json)
    sidecar = _load_model_sidecar(registry_row.artifact_path)
    selected = list(sidecar.get("selected_feature_names", []))
    return selected


def _resolve_selected_features_with_artifact(registry_row: ModelRegistryModel, artifact: dict[str, Any]) -> list[str]:
    selected_features = _resolve_selected_features(registry_row)
    if selected_features:
        return selected_features
    estimator = artifact.get("estimator")
    feature_names = list(getattr(estimator, "feature_names_", []) or [])
    if feature_names:
        return feature_names
    return list(CATBOOST_FALLBACK_FEATURES)


def _resolve_model_shap_summary(registry_row: ModelRegistryModel) -> list[dict] | None:
    if registry_row.shap_summary_json:
        return registry_row.shap_summary_json
    sidecar = _load_model_sidecar(registry_row.artifact_path)
    shap_summary = sidecar.get("shap_summary")
    return shap_summary if isinstance(shap_summary, list) else None


def _infer_engine_cc(engine_displacement_std: str | None, engine_cc: int | None) -> int | None:
    if engine_cc is not None:
        return engine_cc
    if not engine_displacement_std:
        return None
    try:
        return int(round(float(engine_displacement_std.replace(",", ".")) * 1000))
    except (TypeError, ValueError):
        return None


def _safe_decimal(value: Decimal | int | float | None, quantize_to: str = "0.01") -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal(quantize_to))
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    try:
        import numpy as np
    except ImportError:
        np = None

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        try:
            return value.tolist()
        except Exception:
            pass
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if value is None:
        return None
    return value


def _latest_listing_media_subquery():
    ranked_subquery = (
        select(
            StagingMarketplaceListingModel.source_listing_id.label("source_listing_id"),
            StagingMarketplaceListingModel.source_url.label("source_url"),
            StagingMarketplaceListingModel.image_url.label("image_url"),
            func.row_number()
            .over(
                partition_by=StagingMarketplaceListingModel.source_listing_id,
                order_by=StagingMarketplaceListingModel.observed_at.desc(),
            )
            .label("row_number"),
        )
        .subquery()
    )

    return (
        select(
            ranked_subquery.c.source_listing_id,
            ranked_subquery.c.source_url,
            ranked_subquery.c.image_url,
        )
        .where(ranked_subquery.c.row_number == 1)
        .subquery()
    )


def _build_context_counts(
    db: Session,
    *,
    brand: str,
    model: str,
    year: int | None,
    municipality: str | None,
) -> dict[str, float]:
    base_filters = [
        ListingModel.brand_std == brand,
        ListingModel.model_std == model,
        ListingModel.price_cop.is_not(None),
        ListingModel.outlier_flag.is_(False),
        ListingModel.is_active.is_(True),
    ]

    brand_model_count = db.scalar(
        select(func.count()).select_from(ListingModel).where(*base_filters),
    ) or 0

    brand_model_year_count = 0
    if year is not None:
        brand_model_year_count = db.scalar(
            select(func.count()).select_from(ListingModel).where(*base_filters, ListingModel.year == year),
        ) or 0

    brand_model_municipality_count = 0
    if municipality:
        brand_model_municipality_count = db.scalar(
            select(func.count()).select_from(ListingModel).where(
                *base_filters,
                ListingModel.municipality_std == municipality,
            ),
        ) or 0

    return {
        "brand_model_inventory_count": float(brand_model_count),
        "brand_model_year_inventory_count": float(brand_model_year_count),
        "brand_model_municipality_inventory_count": float(brand_model_municipality_count),
    }


def _build_comparables_query(
    request_payload: dict[str, Any],
    *,
    target_year: int | None,
    target_mileage_km: Decimal | None,
    target_price_cop: Decimal | None,
):
    media_subquery = _latest_listing_media_subquery()
    brand = request_payload["brand_std"]
    model = request_payload["model_std"]
    trim = request_payload.get("trim_std")
    transmission = request_payload.get("transmission_std")
    fuel_type = request_payload.get("fuel_type_std")

    score = (
        case((ListingModel.brand_std == brand, 0), else_=25)
        + case((ListingModel.model_std == model, 0), else_=15)
        + case((ListingModel.trim_std == trim, 0), else_=1.0 if trim else 0)
        + case((ListingModel.transmission_std == transmission, 0), else_=0.8 if transmission else 0)
        + case((ListingModel.fuel_type_std == fuel_type, 0), else_=0.8 if fuel_type else 0)
        + (
            func.abs(func.coalesce(ListingModel.year, target_year or 0) - (target_year or 0)) / 1.5
            if target_year is not None
            else 0
        )
        + (
            func.abs(
                func.coalesce(cast(ListingModel.mileage_km, NUMERIC(14, 2)), target_mileage_km or 0)
                - (target_mileage_km or 0)
            )
            / 25000.0
            if target_mileage_km is not None
            else 0
        )
        + (
            func.abs(
                func.coalesce(cast(ListingModel.price_cop, NUMERIC(14, 2)), target_price_cop or 0)
                - (target_price_cop or 0)
            )
            / 12000000.0
            if target_price_cop is not None
            else 0
        )
        + case((ListingModel.municipality_std == request_payload.get("municipality_std"), 0), else_=0.5)
        + case((ListingModel.department_std == request_payload.get("department_std"), 0), else_=0.3)
    ).label("comparable_score")

    return (
        select(
            ListingModel.id,
            ListingModel.source_name,
            ListingModel.source_listing_id,
            media_subquery.c.source_url,
            media_subquery.c.image_url,
            ListingModel.title_clean,
            ListingModel.price_cop,
            ListingModel.year,
            ListingModel.mileage_km,
            ListingModel.brand_std,
            ListingModel.model_std,
            ListingModel.trim_std,
            ListingModel.version_std,
            ListingModel.engine_displacement_std,
            ListingModel.transmission_std,
            ListingModel.fuel_type_std,
            ListingModel.department_std,
            ListingModel.municipality_std,
            ListingModel.locality_std,
            ListingModel.city_std,
            ListingModel.latitude,
            ListingModel.longitude,
            ListingModel.outlier_flag,
            ListingModel.is_active,
            ListingModel.updated_at,
            score,
        )
        .select_from(ListingModel)
        .outerjoin(media_subquery, media_subquery.c.source_listing_id == ListingModel.source_listing_id)
        .where(
            ListingModel.brand_std == brand,
            ListingModel.model_std == model,
            ListingModel.price_cop.is_not(None),
            ListingModel.outlier_flag.is_(False),
            ListingModel.is_active.is_(True),
        )
    )


def _fetch_flexible_comparables(
    db: Session,
    request_payload: dict[str, Any],
    *,
    target_year: int | None,
    target_mileage_km: Decimal | None,
    target_price_cop: Decimal | None,
    limit: int = 8,
) -> tuple[list[ComparableItem], int, int, str]:
    stmt = _build_comparables_query(
        request_payload,
        target_year=target_year,
        target_mileage_km=target_mileage_km,
        target_price_cop=target_price_cop,
    )
    municipality = request_payload.get("municipality_std")
    department = request_payload.get("department_std")
    trim = request_payload.get("trim_std")

    strict_stmt = stmt
    strategy = "brand_model"
    if target_year is not None:
        strict_stmt = strict_stmt.where(ListingModel.year.between(target_year - 1, target_year + 1))
        strategy = "brand_model_year"
    if target_mileage_km is not None:
        mileage_floor = max(target_mileage_km - Decimal("30000"), Decimal("0"))
        mileage_ceiling = target_mileage_km + Decimal("30000")
        strict_stmt = strict_stmt.where(ListingModel.mileage_km.between(mileage_floor, mileage_ceiling))
        strategy = f"{strategy}_km"
    if municipality:
        strict_stmt = strict_stmt.where(ListingModel.municipality_std == municipality)
        strategy = f"{strategy}_municipality"
    elif department:
        strict_stmt = strict_stmt.where(ListingModel.department_std == department)
        strategy = f"{strategy}_department"
    if trim:
        strict_stmt = strict_stmt.where(ListingModel.trim_std == trim)
        strategy = f"{strategy}_trim"

    strict_rows = db.execute(strict_stmt.order_by("comparable_score", ListingModel.updated_at.desc()).limit(limit)).all()
    strict_items = [ComparableItem.model_validate(dict(row._mapping)) for row in strict_rows]
    if len(strict_items) >= min(3, limit):
        return strict_items, len(strict_items), 0, strategy

    relaxed_stmt = stmt
    relaxed_strategy = "brand_model_relaxed"
    if target_year is not None:
        relaxed_stmt = relaxed_stmt.where(ListingModel.year.between(target_year - 2, target_year + 2))
        relaxed_strategy = "brand_model_year_relaxed"
    if target_mileage_km is not None:
        mileage_floor = max(target_mileage_km - Decimal("60000"), Decimal("0"))
        mileage_ceiling = target_mileage_km + Decimal("60000")
        relaxed_stmt = relaxed_stmt.where(ListingModel.mileage_km.between(mileage_floor, mileage_ceiling))
        relaxed_strategy = f"{relaxed_strategy}_km"
    if department:
        relaxed_stmt = relaxed_stmt.where(ListingModel.department_std == department)
        relaxed_strategy = f"{relaxed_strategy}_department"

    relaxed_rows = db.execute(relaxed_stmt.order_by("comparable_score", ListingModel.updated_at.desc()).limit(limit)).all()
    relaxed_items = [ComparableItem.model_validate(dict(row._mapping)) for row in relaxed_rows]
    return relaxed_items, len(strict_items), max(len(relaxed_items) - len(strict_items), 0), relaxed_strategy


def _build_feature_frame(db: Session, payload: dict[str, Any]) -> pd.DataFrame:
    import numpy as np
    import pandas as pd

    brand = payload["brand_std"]
    model = payload["model_std"]
    year = payload.get("year")
    mileage_km = payload.get("mileage_km")
    engine_displacement_std = payload.get("engine_displacement_std")
    engine_cc = _infer_engine_cc(engine_displacement_std, payload.get("engine_cc"))

    vehicle_age = max(CURRENT_YEAR - year, 0) if year is not None else None
    vehicle_age_decimal = Decimal(str(vehicle_age)) if vehicle_age is not None else None
    vehicle_age_bucket = _compute_vehicle_age_bucket(vehicle_age_decimal)
    technomechanical_required_flag = int(vehicle_age is not None and vehicle_age >= 5)
    years_since_technomechanical_threshold = max(vehicle_age - 5, 0) if vehicle_age is not None else 0
    km_per_year = float(mileage_km / vehicle_age) if mileage_km is not None and vehicle_age not in (None, 0) else 0.0
    equipment_score = float(_compute_equipment_score(payload.get("trim_std"), payload.get("version_std")))
    counts = _build_context_counts(
        db,
        brand=brand,
        model=model,
        year=year,
        municipality=payload.get("municipality_std"),
    )

    feature_row: dict[str, Any] = {column: None for column in [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]}
    feature_row.update(
        {
            "year": year,
            "mileage_km": float(mileage_km) if mileage_km is not None else None,
            "engine_cc": engine_cc,
            "vehicle_age": float(vehicle_age) if vehicle_age is not None else None,
            "vehicle_age_squared": float(vehicle_age**2) if vehicle_age is not None else 0.0,
            "is_recent_vehicle_flag": int(vehicle_age is not None and vehicle_age < 3),
            "is_older_vehicle_flag": int(vehicle_age is not None and vehicle_age >= 10),
            "technomechanical_required_flag": technomechanical_required_flag,
            "years_since_technomechanical_threshold": float(years_since_technomechanical_threshold),
            "km_per_year": float(km_per_year),
            "log_mileage_km": float(np.log1p(float(mileage_km or 0))),
            "mileage_per_vehicle_age": float(km_per_year),
            "equipment_score": float(equipment_score),
            "version_rarity_score": 0.0,
            "regional_market_score": 0.0,
            "listing_age_days": 0.0,
            "comparable_inventory_density": float(counts["brand_model_municipality_inventory_count"]),
            "brand_model_inventory_count": counts["brand_model_inventory_count"],
            "brand_model_year_inventory_count": counts["brand_model_year_inventory_count"],
            "brand_model_municipality_inventory_count": counts["brand_model_municipality_inventory_count"],
            "is_premium_brand_flag": int(brand in PREMIUM_BRANDS),
            "hybrid_flag": int(payload.get("hybrid_flag", False)),
            "mhev_flag": int(payload.get("mhev_flag", False)),
            "brand_std": brand,
            "model_std": model,
            "trim_std": payload.get("trim_std"),
            "engine_displacement_std": engine_displacement_std,
            "vehicle_age_bucket": vehicle_age_bucket,
            "transmission_std": payload.get("transmission_std"),
            "fuel_type_std": payload.get("fuel_type_std"),
            "vehicle_type_std": payload.get("vehicle_type_std"),
            "department_std": payload.get("department_std"),
            "municipality_std": payload.get("municipality_std"),
            "locality_std": payload.get("locality_std"),
            "color_std": payload.get("color_std"),
            "brand_model_key": f"{brand}|{model}",
            "brand_model_trim_key": f"{brand}|{model}|{payload.get('trim_std') or 'unknown'}",
        }
    )
    return pd.DataFrame([feature_row], columns=[*NUMERIC_FEATURES, *CATEGORICAL_FEATURES])


def _compute_prediction_explanation(
    registry_row: ModelRegistryModel,
    artifact: dict[str, Any],
    feature_frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    import pandas as pd

    estimator = artifact["estimator"]
    algorithm = artifact["algorithm"]
    selected_features = _resolve_selected_features_with_artifact(registry_row, artifact)

    try:
        if algorithm == "catboost":
            from catboost import Pool

            selected_frame = feature_frame[selected_features].copy() if selected_features else feature_frame.copy()
            cat_feature_indices: list[int] = []
            for index, column in enumerate(selected_frame.columns):
                if column in CATEGORICAL_FEATURES:
                    selected_frame[column] = selected_frame[column].fillna("__missing__").astype(str)
                    cat_feature_indices.append(index)
                else:
                    selected_frame[column] = pd.to_numeric(selected_frame[column], errors="coerce")
            pool = Pool(selected_frame, cat_features=cat_feature_indices)
            shap_values = estimator.get_feature_importance(pool, type="ShapValues")[0][:-1]
            ranking = sorted(
                zip(selected_frame.columns.tolist(), shap_values.tolist(), strict=False),
                key=lambda item: abs(item[1]),
                reverse=True,
            )[:8]
            return [
                {
                    "feature": feature,
                    "shap_value": round(float(value), 6),
                    "direction": "up" if value >= 0 else "down",
                    "feature_value": None
                    if pd.isna(selected_frame.iloc[0][feature])
                    else _json_safe(selected_frame.iloc[0][feature]),
                }
                for feature, value in ranking
            ]
    except Exception as exc:
        LOGGER.warning("No fue posible calcular explicacion local SHAP: %s", exc)

    return []


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "alta"
    if score >= 0.5:
        return "media"
    return "baja"


def _compute_confidence_score(
    *,
    scope_used: str,
    comparables_count: int,
    missing_fields: int,
    inventory_count: float,
    fallback_used: bool,
) -> float:
    score = 0.35
    score += 0.20 if scope_used == "mainstream" else 0.10
    score += min(comparables_count, 10) * 0.03
    score += min(inventory_count, 25) / 25 * 0.15
    score -= missing_fields * 0.06
    if fallback_used:
        score -= 0.10
    return max(0.10, min(score, 0.95))


def _build_confidence_reasons(
    *,
    scope_used: str,
    comparables_count: int,
    missing_fields: int,
    fallback_used: bool,
    inventory_count: float,
) -> list[str]:
    reasons: list[str] = []
    reasons.append(f"scope_usado:{scope_used}")
    if comparables_count >= 5:
        reasons.append("comparables_suficientes")
    elif comparables_count > 0:
        reasons.append("comparables_limitados")
    else:
        reasons.append("sin_comparables")
    if inventory_count >= 15:
        reasons.append("segmento_con_buena_cobertura")
    elif inventory_count > 0:
        reasons.append("segmento_con_cobertura_baja")
    if missing_fields > 0:
        reasons.append(f"campos_faltantes:{missing_fields}")
    if fallback_used:
        reasons.append("uso_modelo_fallback")
    return reasons


def _decimal_percentile(values: list[Decimal], percentile: float) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = Decimal(str(position - lower))
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def predict_market_price(db: Session, request_payload: dict[str, Any]) -> PredictionBundle:
    import numpy as np
    import pandas as pd

    requested_scope = resolve_requested_scope(request_payload["brand_std"])
    registry_row, scope_used = _get_serving_row(db, requested_scope)
    if registry_row is None:
        raise ValueError("No hay modelos registrados disponibles para servir predicciones.")

    artifact = _load_artifact(registry_row.artifact_path)
    feature_frame = _build_feature_frame(db, request_payload)
    estimator = artifact["estimator"]
    algorithm = artifact["algorithm"]
    selected_features = _resolve_selected_features_with_artifact(registry_row, artifact)
    fallback_used = requested_scope != scope_used

    if algorithm == "catboost" and selected_features:
        model_input = feature_frame[selected_features].copy()
        for column in model_input.columns:
            if column in CATEGORICAL_FEATURES:
                model_input[column] = model_input[column].fillna("__missing__").astype(str)
            else:
                model_input[column] = pd.to_numeric(model_input[column], errors="coerce")
        predicted_log = float(estimator.predict(model_input)[0])
    else:
        predicted_log = float(estimator.predict(feature_frame)[0])

    predicted_price = Decimal(str(np.expm1(predicted_log))).quantize(Decimal("0.01"))
    comparables, strict_count, fallback_count, comparables_strategy_used = _fetch_flexible_comparables(
        db,
        request_payload,
        target_year=request_payload.get("year"),
        target_mileage_km=_safe_decimal(request_payload.get("mileage_km")),
        target_price_cop=predicted_price,
        limit=8,
    )

    comparable_prices = [item.price_cop for item in comparables if item.price_cop is not None]
    model_mape = Decimal(str((registry_row.metrics_json or {}).get("mape", 0.25)))
    base_margin = (predicted_price * model_mape).quantize(Decimal("0.01"))
    range_lower = max(predicted_price - base_margin, Decimal("0.00"))
    range_upper = predicted_price + base_margin
    range_method_used = "model_mape_band"
    if len(comparable_prices) >= 3:
        range_lower = ((range_lower + _decimal_percentile(comparable_prices, 0.25)) / 2).quantize(Decimal("0.01"))
        range_upper = ((range_upper + _decimal_percentile(comparable_prices, 0.75)) / 2).quantize(Decimal("0.01"))
        range_method_used = "hybrid_model_plus_comparables"
    elif comparable_prices:
        range_method_used = "model_mape_band_with_sparse_comparables"

    range_lower = min(range_lower, predicted_price)
    range_upper = max(range_upper, predicted_price)
    if range_lower >= range_upper:
        range_lower = max(predicted_price - base_margin, Decimal("0.00"))
        range_upper = predicted_price + base_margin

    missing_fields = sum(
        1
        for field_name in ("year", "mileage_km", "transmission_std", "fuel_type_std", "department_std")
        if not request_payload.get(field_name)
    )
    inventory_count = float(feature_frame.iloc[0]["brand_model_inventory_count"] or 0)
    confidence_score = _compute_confidence_score(
        scope_used=scope_used,
        comparables_count=len(comparable_prices),
        missing_fields=missing_fields,
        inventory_count=inventory_count,
        fallback_used=fallback_used,
    )
    explanation = _compute_prediction_explanation(registry_row, artifact, feature_frame)
    confidence_reasons = _build_confidence_reasons(
        scope_used=scope_used,
        comparables_count=len(comparable_prices),
        missing_fields=missing_fields,
        fallback_used=fallback_used,
        inventory_count=inventory_count,
    )

    response_payload = {
        "predicted_price_cop": predicted_price,
        "predicted_range_lower_cop": range_lower,
        "predicted_range_upper_cop": range_upper,
        "currency": "COP",
        "confidence_score": round(confidence_score, 4),
        "confidence_label": _confidence_label(confidence_score),
        "model_scope_requested": requested_scope,
        "model_scope_used": scope_used,
        "fallback_used": fallback_used,
        "model_registry_id": str(registry_row.id),
        "model_name": registry_row.model_name,
        "model_version": registry_row.model_version,
        "algorithm": registry_row.algorithm,
        "metrics": registry_row.metrics_json or {},
        "comparables_count": len(comparables),
        "strict_comparables_count": strict_count,
        "fallback_comparables_count": fallback_count,
        "comparables_strategy_used": comparables_strategy_used,
        "comparables": [item.model_dump() for item in comparables],
        "top_feature_effects": explanation,
        "local_explanation_available": bool(explanation),
        "model_level_shap_summary": _resolve_model_shap_summary(registry_row) or [],
        "range_method_used": range_method_used,
        "confidence_reasons": confidence_reasons,
    }
    request_payload_json = _json_safe(request_payload)
    response_payload_json = _json_safe(response_payload)

    db.add(
        PredictionLogModel(
            model_registry_id=registry_row.id,
            model_scope_requested=requested_scope,
            model_scope_used=scope_used,
            request_json=request_payload_json,
            response_json=response_payload_json,
            predicted_price_cop=predicted_price,
            confidence_score=Decimal(str(round(confidence_score, 4))),
        )
    )
    db.commit()

    return PredictionBundle(registry_row=registry_row, payload=response_payload)
