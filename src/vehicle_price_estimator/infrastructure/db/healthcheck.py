from sqlalchemy import text

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.session import SessionLocal


LOGGER = get_logger(__name__)


def check_database_connection() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    with SessionLocal() as db:
        result = db.execute(text("SELECT current_database(), current_user, version()")).one()

    LOGGER.info("Database connection successful.")
    LOGGER.info("Database: %s", result[0])
    LOGGER.info("User: %s", result[1])
    LOGGER.info("Version: %s", result[2])
