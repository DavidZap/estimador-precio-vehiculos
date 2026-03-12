from sqlalchemy import text

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.base import Base
from vehicle_price_estimator.infrastructure.db.session import engine
from vehicle_price_estimator.infrastructure.db.models import model_registry  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import pipeline_run  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import price_history  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import raw_listing_payload  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import raw_run  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import vehicle  # noqa: F401


LOGGER = get_logger(__name__)


def initialize_database() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    schemas = ("raw", "staging", "core", "ml", "ops")

    with engine.begin() as connection:
        for schema_name in schemas:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))

        Base.metadata.create_all(bind=connection)

    LOGGER.info("Database initialized successfully.")

