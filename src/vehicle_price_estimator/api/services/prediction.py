from __future__ import annotations

from sqlalchemy.orm import Session

from vehicle_price_estimator.api.schemas.prediction import ActiveModelsResponse, PredictionRequest, PredictionResponse
from vehicle_price_estimator.infrastructure.ml.serving.predictor import get_active_serving_models, predict_market_price


def get_active_models_service(db: Session) -> ActiveModelsResponse:
    return ActiveModelsResponse(items=get_active_serving_models(db))


def predict_vehicle_price_service(db: Session, request: PredictionRequest) -> PredictionResponse:
    prediction = predict_market_price(db, request.model_dump())
    return PredictionResponse.model_validate(prediction.payload)
