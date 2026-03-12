from sqlalchemy import text

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.base import Base
from vehicle_price_estimator.infrastructure.db.session import engine
from vehicle_price_estimator.infrastructure.db.models import location_reference  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import listing_feature  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import listing_status_history  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import model_registry  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import pipeline_run  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import price_history  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import raw_listing_payload  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import raw_run  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import staging_listing  # noqa: F401
from vehicle_price_estimator.infrastructure.db.models import vehicle  # noqa: F401


LOGGER = get_logger(__name__)


DDL_STATEMENTS = [
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS trim_std VARCHAR(120)",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS engine_displacement_std VARCHAR(20)",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS engine_cc INTEGER",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS hybrid_flag BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS mhev_flag BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS variant_raw TEXT",
    "ALTER TABLE core.vehicle_canonical ADD COLUMN IF NOT EXISTS marketing_tokens_json JSONB",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS trim_std VARCHAR(120)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS engine_displacement_std VARCHAR(20)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS engine_cc INTEGER",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS hybrid_flag BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS mhev_flag BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS variant_raw TEXT",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS marketing_tokens_json JSONB",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS department_std VARCHAR(120)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS municipality_std VARCHAR(120)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS locality_std VARCHAR(120)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS municipality_code VARCHAR(10)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS latitude NUMERIC(12,8)",
    "ALTER TABLE core.listings ADD COLUMN IF NOT EXISTS longitude NUMERIC(12,8)",
]


def initialize_database() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    schemas = ("raw", "staging", "core", "ml", "ops", "ref")

    with engine.begin() as connection:
        for schema_name in schemas:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))

        Base.metadata.create_all(bind=connection)
        for statement in DDL_STATEMENTS:
            connection.execute(text(statement))

    LOGGER.info("Database initialized successfully.")
