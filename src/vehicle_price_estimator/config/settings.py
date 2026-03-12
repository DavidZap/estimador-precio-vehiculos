from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="vehicle-price-estimator", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:[YOUR_PASSWORD]@[YOUR_SUPABASE_HOST]:5432/postgres",
        alias="DATABASE_URL",
    )
    database_ssl_mode: str | None = Field(default="require", alias="DATABASE_SSL_MODE")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, alias="DATABASE_POOL_TIMEOUT")
    database_pool_recycle: int = Field(default=1800, alias="DATABASE_POOL_RECYCLE")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    mercadolibre_site_id: str = Field(default="MCO", alias="MERCADOLIBRE_SITE_ID")
    mercadolibre_api_base_url: str = Field(
        default="https://api.mercadolibre.com",
        alias="MERCADOLIBRE_API_BASE_URL",
    )
    mercadolibre_web_base_url: str = Field(
        default="https://listado.mercadolibre.com.co",
        alias="MERCADOLIBRE_WEB_BASE_URL",
    )
    mercadolibre_timeout_seconds: int = Field(default=30, alias="MERCADOLIBRE_TIMEOUT_SECONDS")
    mercadolibre_default_limit: int = Field(default=20, alias="MERCADOLIBRE_DEFAULT_LIMIT")
    mercadolibre_enable_browser_fallback: bool = Field(
        default=True,
        alias="MERCADOLIBRE_ENABLE_BROWSER_FALLBACK",
    )
    mercadolibre_browser_headless: bool = Field(
        default=True,
        alias="MERCADOLIBRE_BROWSER_HEADLESS",
    )
    mercadolibre_browser_wait_ms: int = Field(default=8000, alias="MERCADOLIBRE_BROWSER_WAIT_MS")
    raw_storage_path: Path = Field(default=Path("./data/raw"), alias="RAW_STORAGE_PATH")
    artifacts_path: Path = Field(default=Path("./data/artifacts"), alias="ARTIFACTS_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.raw_storage_path.mkdir(parents=True, exist_ok=True)
    settings.artifacts_path.mkdir(parents=True, exist_ok=True)
    return settings
