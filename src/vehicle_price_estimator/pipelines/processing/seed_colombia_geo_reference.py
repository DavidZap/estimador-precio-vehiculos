from __future__ import annotations

import unicodedata
from decimal import Decimal
from decimal import InvalidOperation

import httpx

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.location_reference import (
    ColombiaLocationReferenceModel,
)
from vehicle_price_estimator.infrastructure.db.session import SessionLocal


LOGGER = get_logger(__name__)


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(ascii_value.title().split())


def _parse_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def seed_colombia_geo_reference() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    response = httpx.get(settings.colombia_geo_source_url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", [])

    with SessionLocal() as db:
        existing = {
            row.municipality_code: row
            for row in db.query(ColombiaLocationReferenceModel).all()
        }

        inserted = 0
        updated = 0

        for row in rows:
            department_code = row[8]
            department_name = row[9]
            municipality_code = row[10]
            city_name = row[11]
            municipality_type = row[12]
            longitude = _parse_decimal(row[13])
            latitude = _parse_decimal(row[14])

            record = existing.get(municipality_code)
            if record is None:
                record = ColombiaLocationReferenceModel(
                    department_code=department_code,
                    department_name=department_name,
                    department_name_std=_normalize_name(department_name),
                    municipality_code=municipality_code,
                    city_name=city_name,
                    city_name_std=_normalize_name(city_name),
                    municipality_type=municipality_type,
                    longitude=longitude,
                    latitude=latitude,
                )
                db.add(record)
                inserted += 1
            else:
                record.department_code = department_code
                record.department_name = department_name
                record.department_name_std = _normalize_name(department_name)
                record.city_name = city_name
                record.city_name_std = _normalize_name(city_name)
                record.municipality_type = municipality_type
                record.longitude = longitude
                record.latitude = latitude
                updated += 1

        db.commit()

    LOGGER.info("Geo reference seeded successfully. inserted=%s updated=%s", inserted, updated)
