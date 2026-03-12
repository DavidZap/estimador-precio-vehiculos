from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vehicle_price_estimator.api.deps import get_db
from vehicle_price_estimator.api.schemas.prediction import ActiveModelsResponse, PredictionRequest, PredictionResponse
from vehicle_price_estimator.api.services.prediction import get_active_models_service, predict_vehicle_price_service


router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/models/active", response_model=ActiveModelsResponse)
def get_active_models(db: Session = Depends(get_db)) -> ActiveModelsResponse:
    return get_active_models_service(db)


@router.post("/estimate", response_model=PredictionResponse)
def estimate_vehicle_price(
    request: PredictionRequest,
    db: Session = Depends(get_db),
) -> PredictionResponse:
    return predict_vehicle_price_service(db, request)
