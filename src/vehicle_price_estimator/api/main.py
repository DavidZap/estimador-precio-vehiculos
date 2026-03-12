from contextlib import asynccontextmanager

from fastapi import FastAPI

from vehicle_price_estimator.api.routers import health, market, meta, prediction
from vehicle_price_estimator.config.logging import configure_logging
from vehicle_price_estimator.config.settings import get_settings


settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="Vehicle Price Estimator API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
def application_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(market.router, prefix=settings.api_prefix)
app.include_router(meta.router, prefix=settings.api_prefix)
app.include_router(prediction.router, prefix=settings.api_prefix)
