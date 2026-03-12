from fastapi import APIRouter

from vehicle_price_estimator.config.settings import get_settings


router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/settings")
def get_runtime_settings() -> dict[str, str | int | bool]:
    settings = get_settings()
    masked_database_url = settings.database_url
    if "@" in masked_database_url and "://" in masked_database_url:
        prefix, suffix = masked_database_url.split("://", maxsplit=1)
        if "@" in suffix:
            credentials, host = suffix.split("@", maxsplit=1)
            if ":" in credentials:
                user, _ = credentials.split(":", maxsplit=1)
                masked_database_url = f"{prefix}://{user}:***@{host}"

    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "api_prefix": settings.api_prefix,
        "app_debug": settings.app_debug,
        "app_port": settings.app_port,
        "database_url_masked": masked_database_url,
        "database_ssl_mode": settings.database_ssl_mode or "disabled",
    }
