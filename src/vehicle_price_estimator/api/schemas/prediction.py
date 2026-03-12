from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vehicle_price_estimator.api.schemas.market import ComparableItem


class PredictionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    brand_std: str = Field(..., min_length=1)
    model_std: str = Field(..., min_length=1)
    trim_std: str | None = None
    version_std: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    mileage_km: Decimal | None = Field(default=None, ge=0)
    engine_displacement_std: str | None = None
    engine_cc: int | None = Field(default=None, ge=0)
    transmission_std: str | None = None
    fuel_type_std: str | None = None
    vehicle_type_std: str | None = None
    color_std: str | None = None
    department_std: str | None = None
    municipality_std: str | None = None
    locality_std: str | None = None
    hybrid_flag: bool = False
    mhev_flag: bool = False


class PredictionFeatureEffect(BaseModel):
    feature: str
    shap_value: float | None = None
    mean_abs_shap: float | None = None
    direction: str | None = None
    feature_value: Any | None = None


class ActiveModelInfo(BaseModel):
    registry_id: UUID
    model_name: str
    model_version: str
    algorithm: str
    model_scope: str
    status: str
    is_active: bool
    metrics: dict[str, Any]
    scope_filters: dict[str, Any]
    selected_features: list[str]
    shap_summary: list[dict[str, Any]] | None = None


class PredictionResponse(BaseModel):
    predicted_price_cop: Decimal
    predicted_range_lower_cop: Decimal
    predicted_range_upper_cop: Decimal
    currency: str
    confidence_score: float
    confidence_label: str
    model_scope_requested: str
    model_scope_used: str
    fallback_used: bool
    model_registry_id: UUID
    model_name: str
    model_version: str
    algorithm: str
    metrics: dict[str, Any]
    comparables_count: int
    strict_comparables_count: int
    fallback_comparables_count: int
    comparables_strategy_used: str
    comparables: list[ComparableItem]
    top_feature_effects: list[PredictionFeatureEffect]
    local_explanation_available: bool
    model_level_shap_summary: list[dict[str, Any]] | None = None
    range_method_used: str
    confidence_reasons: list[str]


class ActiveModelsResponse(BaseModel):
    items: list[ActiveModelInfo]
