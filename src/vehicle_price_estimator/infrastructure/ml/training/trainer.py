from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import warnings
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from vehicle_price_estimator.config.logging import get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.model_registry import ModelRegistryModel
from vehicle_price_estimator.infrastructure.db.models.pipeline_run import PipelineRunModel
from vehicle_price_estimator.infrastructure.db.session import SessionLocal
from vehicle_price_estimator.infrastructure.ml.features.dataset_builder import (
    CATEGORICAL_FEATURES,
    IDENTIFIER_COLUMNS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    TrainingDataset,
    build_training_dataset,
)
from vehicle_price_estimator.infrastructure.ml.serving.scopes import (
    infer_model_scope,
    normalize_brand_list,
    resolve_registry_scope,
)


LOGGER = get_logger(__name__)


@dataclass(slots=True)
class ModelCandidateResult:
    model_name: str
    algorithm: str
    model_version: str
    metrics: dict[str, float]
    params: dict
    artifact_path: Path
    dataset_id: uuid.UUID
    feature_schema: dict
    trained_at: datetime
    selected_feature_names: list[str]
    model_scope: str
    scope_filters: dict
    shap_summary: list[dict] | None = None


RAW_FEATURE_PRIORITY = [
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


def _build_preprocessor() -> ColumnTransformer:
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_FEATURES),
            ("cat", categorical_transformer, CATEGORICAL_FEATURES),
        ]
    )


def _build_selector() -> SelectFromModel:
    return SelectFromModel(
        estimator=ElasticNet(alpha=0.0005, l1_ratio=0.9, random_state=42, max_iter=5000),
        threshold="median",
        max_features=80,
    )


def _build_dense_preprocessor() -> ColumnTransformer:
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_FEATURES),
            ("cat", categorical_transformer, CATEGORICAL_FEATURES),
        ]
    )


def _split_dataset(dataset: TrainingDataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    dataframe = dataset.dataframe.copy()
    dataframe = dataframe.sort_values(["first_seen_at", "updated_at"], na_position="last")
    split_index = max(int(len(dataframe) * 0.8), 1)
    if split_index >= len(dataframe):
        split_index = len(dataframe) - 1
    if split_index <= 0:
        raise ValueError("No hay suficientes filas para separar train/test.")
    return dataframe.iloc[:split_index].copy(), dataframe.iloc[split_index:].copy()


def _apply_train_only_context_features(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = train_df.copy()
    test_df = test_df.copy()

    group_keys = {
        "brand_model_inventory_count": ["brand_std", "model_std"],
        "brand_model_year_inventory_count": ["brand_std", "model_std", "year"],
        "brand_model_municipality_inventory_count": ["brand_std", "model_std", "municipality_std"],
    }

    for feature_name, group_columns in group_keys.items():
        grouped = (
            train_df.groupby(group_columns, dropna=False)["listing_id"]
            .count()
            .rename(feature_name)
            .reset_index()
        )
        train_df = train_df.drop(columns=[feature_name], errors="ignore").merge(
            grouped,
            on=group_columns,
            how="left",
        )
        test_df = test_df.drop(columns=[feature_name], errors="ignore").merge(
            grouped,
            on=group_columns,
            how="left",
        )
        train_df[feature_name] = train_df[feature_name].fillna(0).astype(float)
        test_df[feature_name] = test_df[feature_name].fillna(0).astype(float)

    return train_df, test_df


def _prepare_xy(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    feature_columns = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]
    X = dataframe[feature_columns].copy()
    y = np.log1p(dataframe[TARGET_COLUMN].astype(float).to_numpy())
    return X, y


def _select_raw_feature_columns(dataframe: pd.DataFrame) -> list[str]:
    selected: list[str] = []
    for column in RAW_FEATURE_PRIORITY:
        if column not in dataframe.columns:
            continue
        series = dataframe[column]
        missing_ratio = float(series.isna().mean())
        unique_count = int(series.nunique(dropna=True))
        essential = column in {"brand_std", "model_std", "year", "mileage_km"}
        if not essential and missing_ratio > 0.75:
            continue
        if unique_count <= 1:
            continue
        selected.append(column)
    return selected


def _extract_selected_feature_names(estimator: Pipeline, input_frame: pd.DataFrame) -> list[str]:
    preprocessor = estimator.named_steps["preprocessor"]
    feature_names = list(preprocessor.get_feature_names_out())
    selector = estimator.named_steps.get("selector")
    if selector is not None:
        support_mask = selector.get_support()
        feature_names = [name for name, keep in zip(feature_names, support_mask, strict=False) if keep]
    return feature_names


def _prepare_shap_payload(estimator, algorithm: str, X_test: pd.DataFrame) -> tuple[object, list[str]] | tuple[None, list[str]]:
    if algorithm == "catboost":
        return X_test, list(X_test.columns)

    if not isinstance(estimator, Pipeline):
        return None, []

    transformed = estimator.named_steps["preprocessor"].transform(X_test)
    selector = estimator.named_steps.get("selector")
    if selector is not None:
        transformed = selector.transform(transformed)

    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()

    return transformed, _extract_selected_feature_names(estimator, X_test)


def _compute_shap_summary(model, algorithm: str, shap_input, feature_names: list[str]) -> list[dict] | None:
    try:
        import shap
    except ImportError:
        LOGGER.warning("SHAP no está instalado; se omite explicabilidad.")
        return None

    if shap_input is None or not feature_names:
        return None

    try:
        sample_size = min(len(shap_input), 200)
        if hasattr(shap_input, "iloc"):
            sample = shap_input.iloc[:sample_size].copy()
        else:
            sample = shap_input[:sample_size]

        if algorithm == "catboost":
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(sample)
            values = np.abs(np.array(shap_values))
        else:
            explainer = shap.Explainer(model, sample)
            shap_values = explainer(sample)
            values = np.abs(shap_values.values)
        if values.ndim == 3:
            values = values.mean(axis=0)
        mean_abs = values.mean(axis=0)
        ranking = sorted(
            zip(feature_names, mean_abs, strict=False),
            key=lambda item: item[1],
            reverse=True,
        )[:15]
        return [
            {"feature": feature, "mean_abs_shap": round(float(score), 6)}
            for feature, score in ranking
        ]
    except Exception as exc:
        LOGGER.warning("No fue posible calcular SHAP para %s: %s", algorithm, exc)
        return None


def _evaluate_predictions(y_true_log: np.ndarray, y_pred_log: np.ndarray) -> dict[str, float]:
    y_true = np.expm1(y_true_log)
    y_pred = np.expm1(y_pred_log)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mape = float(mean_absolute_percentage_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 6),
        "r2": round(r2, 6),
    }


def _optional_model_candidates() -> list[tuple[str, str, object, dict]]:
    candidates: list[tuple[str, str, object, dict]] = []

    try:
        from catboost import CatBoostRegressor

        candidates.append(
            (
                "market_price_catboost",
                "catboost",
                CatBoostRegressor(
                    depth=8,
                    iterations=500,
                    learning_rate=0.05,
                    loss_function="RMSE",
                    verbose=False,
                    random_seed=42,
                ),
                {
                    "depth": 8,
                    "iterations": 500,
                    "learning_rate": 0.05,
                    "loss_function": "RMSE",
                },
            )
        )
    except ImportError:
        LOGGER.warning("CatBoost no está instalado; se omite ese candidato.")

    try:
        from lightgbm import LGBMRegressor

        candidates.append(
            (
                "market_price_lightgbm",
                "lightgbm",
                Pipeline(
                    steps=[
                        ("preprocessor", _build_dense_preprocessor()),
                        ("selector", _build_selector()),
                        (
                            "model",
                            LGBMRegressor(
                                n_estimators=500,
                                learning_rate=0.05,
                                num_leaves=31,
                                random_state=42,
                                verbose=-1,
                            ),
                        ),
                    ]
                ),
                {
                    "n_estimators": 500,
                    "learning_rate": 0.05,
                    "num_leaves": 31,
                },
            )
        )
    except ImportError:
        LOGGER.warning("LightGBM no está instalado; se omite ese candidato.")

    try:
        from xgboost import XGBRegressor

        candidates.append(
            (
                "market_price_xgboost",
                "xgboost",
                Pipeline(
                    steps=[
                        ("preprocessor", _build_dense_preprocessor()),
                        ("selector", _build_selector()),
                        (
                            "model",
                            XGBRegressor(
                                n_estimators=400,
                                learning_rate=0.05,
                                max_depth=8,
                                subsample=0.9,
                                colsample_bytree=0.9,
                                objective="reg:squarederror",
                                random_state=42,
                            ),
                        ),
                    ]
                ),
                {
                    "n_estimators": 400,
                    "learning_rate": 0.05,
                    "max_depth": 8,
                    "subsample": 0.9,
                    "colsample_bytree": 0.9,
                },
            )
        )
    except ImportError:
        LOGGER.warning("XGBoost no está instalado; se omite ese candidato.")

    return candidates


def _baseline_candidates() -> list[tuple[str, str, object, dict]]:
    return [
        (
            "market_price_elasticnet",
            "elasticnet",
            Pipeline(
                steps=[
                    ("preprocessor", _build_preprocessor()),
                    ("selector", _build_selector()),
                    ("model", ElasticNet(alpha=0.0008, l1_ratio=0.15, random_state=42, max_iter=5000)),
                ]
            ),
            {"alpha": 0.0008, "l1_ratio": 0.15, "max_iter": 5000},
        ),
        (
            "market_price_random_forest",
            "random_forest",
            Pipeline(
                steps=[
                    ("preprocessor", _build_dense_preprocessor()),
                    ("selector", _build_selector()),
                    (
                        "model",
                        RandomForestRegressor(
                            n_estimators=300,
                            max_depth=18,
                            min_samples_leaf=2,
                            random_state=42,
                            n_jobs=-1,
                        ),
                    ),
                ]
            ),
            {"n_estimators": 300, "max_depth": 18, "min_samples_leaf": 2},
        ),
        (
            "market_price_hist_gradient_boosting",
            "hist_gradient_boosting",
            Pipeline(
                steps=[
                    ("preprocessor", _build_dense_preprocessor()),
                    ("selector", _build_selector()),
                    (
                        "model",
                        HistGradientBoostingRegressor(
                            learning_rate=0.05,
                            max_depth=10,
                            max_iter=500,
                            random_state=42,
                        ),
                    ),
                ]
            ),
            {"learning_rate": 0.05, "max_depth": 10, "max_iter": 500},
        ),
    ]


def _fit_candidate(model_name: str, algorithm: str, estimator, params: dict, dataset: TrainingDataset) -> ModelCandidateResult:
    train_df, test_df = _split_dataset(dataset)
    train_df, test_df = _apply_train_only_context_features(train_df, test_df)
    X_train, y_train = _prepare_xy(train_df)
    X_test, y_test = _prepare_xy(test_df)
    selected_feature_names: list[str] = []
    shap_summary: list[dict] | None = None

    if algorithm == "catboost":
        selected_columns = _select_raw_feature_columns(train_df)
        X_train_cb = X_train[selected_columns].copy()
        X_test_cb = X_test[selected_columns].copy()
        categorical_features = [column for column in selected_columns if column in CATEGORICAL_FEATURES]
        for column in categorical_features:
            X_train_cb[column] = X_train_cb[column].fillna("__missing__").astype(str)
            X_test_cb[column] = X_test_cb[column].fillna("__missing__").astype(str)
        for column in [column for column in selected_columns if column in NUMERIC_FEATURES]:
            X_train_cb[column] = pd.to_numeric(X_train_cb[column], errors="coerce")
            X_test_cb[column] = pd.to_numeric(X_test_cb[column], errors="coerce")
        estimator.fit(X_train_cb, y_train, cat_features=categorical_features)
        predictions = estimator.predict(X_test_cb)
        selected_feature_names = selected_columns
        shap_summary = _compute_shap_summary(estimator, algorithm, X_test_cb, selected_feature_names)
    else:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names, but LGBMRegressor was fitted with feature names",
            )
            estimator.fit(X_train, y_train)
            predictions = estimator.predict(X_test)
        selected_feature_names = _extract_selected_feature_names(estimator, X_train)
        shap_input, shap_feature_names = _prepare_shap_payload(estimator, algorithm, X_test)
        final_model = estimator.named_steps["model"] if isinstance(estimator, Pipeline) else estimator
        shap_summary = _compute_shap_summary(final_model, algorithm, shap_input, shap_feature_names or selected_feature_names)

    metrics = _evaluate_predictions(y_test, predictions)

    settings = get_settings()
    model_version = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    model_dir = settings.artifacts_path / "training" / "models" / model_name / model_version
    model_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = model_dir / "model.joblib"
    metadata_path = model_dir / "metadata.json"

    joblib.dump(
        {
            "estimator": estimator,
            "algorithm": algorithm,
            "model_name": model_name,
            "model_version": model_version,
            "numeric_features": NUMERIC_FEATURES,
            "categorical_features": CATEGORICAL_FEATURES,
            "target_column": TARGET_COLUMN,
            "dataset_id": str(dataset.dataset_id),
        },
        artifact_path,
    )
    metadata_path.write_text(
        json.dumps(
            {
                "model_name": model_name,
                "algorithm": algorithm,
                "model_version": model_version,
                "params": params,
                "metrics": metrics,
                "dataset_id": str(dataset.dataset_id),
                "trained_at": datetime.now(UTC).isoformat(),
                "selected_feature_names": selected_feature_names,
                "shap_summary": shap_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return ModelCandidateResult(
        model_name=model_name,
        algorithm=algorithm,
        model_version=model_version,
        metrics=metrics,
        params=params,
        artifact_path=artifact_path,
        dataset_id=dataset.dataset_id,
        feature_schema=dataset.feature_schema,
        trained_at=datetime.now(UTC),
        selected_feature_names=selected_feature_names,
        model_scope="global",
        scope_filters={},
        shap_summary=shap_summary,
    )


def _register_candidate(result: ModelCandidateResult) -> uuid.UUID:
    with SessionLocal() as db:
        registry_row = ModelRegistryModel(
            model_name=result.model_name,
            model_version=result.model_version,
            algorithm=result.algorithm,
            dataset_id=result.dataset_id,
            artifact_path=str(result.artifact_path),
            metrics_json=result.metrics,
            params_json=result.params,
            feature_schema_json=result.feature_schema,
            selected_features_json=result.selected_feature_names,
            shap_summary_json=result.shap_summary,
            model_scope=result.model_scope,
            scope_filters_json=result.scope_filters,
            status="trained",
            is_active=False,
        )
        db.add(registry_row)
        db.commit()
        db.refresh(registry_row)
        return registry_row.id


def _promote_if_better(result: ModelCandidateResult, registry_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        active_model = next(
            (
                row
                for row in db.query(ModelRegistryModel)
                .filter(ModelRegistryModel.is_active.is_(True))
                .order_by(ModelRegistryModel.created_at.desc())
                .all()
                if resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json)
                == result.model_scope
            ),
            None,
        )

        should_promote = active_model is None
        if active_model is not None:
            active_mae = float((active_model.metrics_json or {}).get("mae", float("inf")))
            should_promote = result.metrics["mae"] < active_mae

        if not should_promote:
            return False

        if active_model is not None:
            active_model.is_active = False
            active_model.status = "archived"

        candidate_row = db.query(ModelRegistryModel).filter(ModelRegistryModel.id == registry_id).one()
        candidate_row.is_active = True
        candidate_row.status = "promoted"
        candidate_row.promoted_at = datetime.now(UTC)
        db.commit()
        return True


def run_training_pipeline(
    *,
    min_year: int = 2010,
    exclude_outliers: bool = True,
    active_only: bool = True,
    include_brands: list[str] | None = None,
    min_model_rows: int = 1,
    promote: bool = True,
) -> dict:
    started_at = datetime.now(UTC)
    normalized_brands = normalize_brand_list(include_brands)
    model_scope = infer_model_scope(normalized_brands)
    scope_filters = {
        "include_brands": normalized_brands,
        "min_model_rows": min_model_rows,
    }
    with SessionLocal() as db:
        pipeline_run = PipelineRunModel(
            pipeline_name="training_pipeline_v0_1",
            status="running",
            context_json={
                "min_year": min_year,
                "exclude_outliers": exclude_outliers,
                "active_only": active_only,
                "include_brands": normalized_brands,
                "min_model_rows": min_model_rows,
                "model_scope": model_scope,
                "promote": promote,
            },
            started_at=started_at,
        )
        db.add(pipeline_run)
        db.commit()
        db.refresh(pipeline_run)
        pipeline_run_id = pipeline_run.id

    try:
        dataset = build_training_dataset(
            min_year=min_year,
            exclude_outliers=exclude_outliers,
            active_only=active_only,
            include_brands=normalized_brands,
            min_model_rows=min_model_rows,
        )

        candidates = _baseline_candidates()
        candidates.extend(_optional_model_candidates())
        if not candidates:
            raise ValueError("No hay candidatos de entrenamiento disponibles.")

        results: list[tuple[uuid.UUID, ModelCandidateResult]] = []
        for model_name, algorithm, estimator, params in candidates:
            result = _fit_candidate(model_name, algorithm, estimator, params, dataset)
            result.model_scope = model_scope
            result.scope_filters = scope_filters
            registry_id = _register_candidate(result)
            results.append((registry_id, result))

        best_registry_id, best_result = sorted(
            results,
            key=lambda item: (item[1].metrics["mae"], item[1].metrics["rmse"]),
        )[0]
        promoted = _promote_if_better(best_result, best_registry_id) if promote else False

        summary = {
            "dataset_id": str(dataset.dataset_id),
            "dataset_path": str(dataset.dataset_path),
            "row_count": int(len(dataset.dataframe)),
            "candidate_count": len(results),
            "include_brands": normalized_brands,
            "min_model_rows": min_model_rows,
            "model_scope": model_scope,
            "best_model_name": best_result.model_name,
            "best_algorithm": best_result.algorithm,
            "best_metrics": best_result.metrics,
            "best_selected_features": best_result.selected_feature_names,
            "best_shap_summary": best_result.shap_summary,
            "promoted": promoted,
            "candidates": [
                {
                    "registry_id": str(registry_id),
                    "model_name": result.model_name,
                    "algorithm": result.algorithm,
                    "metrics": result.metrics,
                    "selected_feature_count": len(result.selected_feature_names),
                }
                for registry_id, result in results
            ],
        }

        with SessionLocal() as db:
            pipeline_run = db.query(PipelineRunModel).filter(PipelineRunModel.id == pipeline_run_id).one()
            pipeline_run.status = "completed"
            pipeline_run.metrics_json = summary
            pipeline_run.finished_at = datetime.now(UTC)
            db.commit()

        return summary
    except Exception as exc:
        with SessionLocal() as db:
            pipeline_run = db.query(PipelineRunModel).filter(PipelineRunModel.id == pipeline_run_id).one()
            pipeline_run.status = "failed"
            pipeline_run.error_json = {"error": str(exc), "error_type": type(exc).__name__}
            pipeline_run.finished_at = datetime.now(UTC)
            db.commit()
        raise


def promote_model(registry_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        candidate = db.query(ModelRegistryModel).filter(ModelRegistryModel.id == registry_id).one_or_none()
        if candidate is None:
            raise ValueError(f"No existe modelo con id {registry_id}")
        candidate_scope = resolve_registry_scope(
            candidate.model_scope,
            candidate.scope_filters_json,
            candidate.feature_schema_json,
        )

        active_model = next(
            (
                row
                for row in db.query(ModelRegistryModel)
                .filter(ModelRegistryModel.is_active.is_(True))
                .order_by(ModelRegistryModel.created_at.desc())
                .all()
                if resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json)
                == candidate_scope
            ),
            None,
        )

        if active_model is not None and active_model.id == candidate.id:
            return True

        candidate_mae = float((candidate.metrics_json or {}).get("mae", float("inf")))
        active_mae = float((active_model.metrics_json or {}).get("mae", float("inf"))) if active_model else float("inf")
        if active_model is not None and candidate_mae >= active_mae:
            return False

        if active_model is not None:
            active_model.is_active = False
            active_model.status = "archived"

        candidate.is_active = True
        candidate.model_scope = candidate_scope
        candidate.status = "promoted"
        candidate.promoted_at = datetime.now(UTC)
        db.commit()
        return True


def force_promote_model(registry_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        candidate = db.query(ModelRegistryModel).filter(ModelRegistryModel.id == registry_id).one_or_none()
        if candidate is None:
            raise ValueError(f"No existe modelo con id {registry_id}")

        candidate_scope = resolve_registry_scope(
            candidate.model_scope,
            candidate.scope_filters_json,
            candidate.feature_schema_json,
        )

        active_models = (
            db.query(ModelRegistryModel)
            .filter(ModelRegistryModel.is_active.is_(True))
            .order_by(ModelRegistryModel.created_at.desc())
            .all()
        )
        for active in active_models:
            if resolve_registry_scope(active.model_scope, active.scope_filters_json, active.feature_schema_json) == candidate_scope:
                active.is_active = False
                active.status = "archived"

        candidate.is_active = True
        candidate.model_scope = candidate_scope
        candidate.status = "promoted"
        candidate.promoted_at = datetime.now(UTC)
        db.commit()
        return True


def promote_latest_model_for_scope(scope: str) -> uuid.UUID | None:
    with SessionLocal() as db:
        candidates = [
            row
            for row in db.query(ModelRegistryModel).order_by(ModelRegistryModel.created_at.desc()).all()
            if resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json) == scope
        ]
        if not candidates:
            return None

        best_candidate = min(
            candidates,
            key=lambda row: (
                float((row.metrics_json or {}).get("mae", float("inf"))),
                float((row.metrics_json or {}).get("rmse", float("inf"))),
            ),
        )
        promote_model(best_candidate.id)
        return best_candidate.id


def promote_preferred_model_for_scope(scope: str, preferred_algorithm: str) -> uuid.UUID | None:
    with SessionLocal() as db:
        candidates = [
            row
            for row in db.query(ModelRegistryModel).order_by(ModelRegistryModel.created_at.desc()).all()
            if resolve_registry_scope(row.model_scope, row.scope_filters_json, row.feature_schema_json) == scope
        ]
        if not candidates:
            return None

        preferred_candidates = [
            row for row in candidates if (row.algorithm or "").strip().lower() == preferred_algorithm.strip().lower()
        ]
        if preferred_candidates:
            chosen = min(
                preferred_candidates,
                key=lambda row: (
                    float((row.metrics_json or {}).get("mae", float("inf"))),
                    float((row.metrics_json or {}).get("rmse", float("inf"))),
                ),
            )
        else:
            chosen = min(
                candidates,
                key=lambda row: (
                    float((row.metrics_json or {}).get("mae", float("inf"))),
                    float((row.metrics_json or {}).get("rmse", float("inf"))),
                ),
            )

        active_models = (
            db.query(ModelRegistryModel)
            .filter(ModelRegistryModel.is_active.is_(True))
            .order_by(ModelRegistryModel.created_at.desc())
            .all()
        )
        for active in active_models:
            if resolve_registry_scope(active.model_scope, active.scope_filters_json, active.feature_schema_json) == scope:
                active.is_active = False
                active.status = "archived"

        chosen.is_active = True
        chosen.model_scope = scope
        chosen.status = "promoted"
        chosen.promoted_at = datetime.now(UTC)
        db.commit()
        return chosen.id
