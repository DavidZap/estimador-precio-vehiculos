from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from vehicle_price_estimator.api.deps import get_db


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/db")
def database_health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}

