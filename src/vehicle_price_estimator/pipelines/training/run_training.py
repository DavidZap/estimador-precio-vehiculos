from __future__ import annotations

from vehicle_price_estimator.config.logging import configure_logging
from vehicle_price_estimator.config.settings import get_settings


def run_training(
    *,
    min_year: int = 2010,
    exclude_outliers: bool = True,
    active_only: bool = True,
    include_brands: list[str] | None = None,
    min_model_rows: int = 1,
    promote: bool = True,
) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    from vehicle_price_estimator.infrastructure.ml.training.trainer import run_training_pipeline

    return run_training_pipeline(
        min_year=min_year,
        exclude_outliers=exclude_outliers,
        active_only=active_only,
        include_brands=include_brands,
        min_model_rows=min_model_rows,
        promote=promote,
    )
