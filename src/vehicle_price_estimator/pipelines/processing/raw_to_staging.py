from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.raw_run import ExtractRunModel
from vehicle_price_estimator.infrastructure.db.models.staging_listing import (
    StagingMarketplaceListingModel,
)
from vehicle_price_estimator.infrastructure.db.session import SessionLocal


LOGGER = get_logger(__name__)


@dataclass(slots=True)
class SearchCardRecord:
    source_listing_id: str
    source_url: str
    title_raw: str | None
    price_amount: Decimal | None
    location_raw: str | None
    city_raw: str | None
    state_raw: str | None
    brand_raw: str | None
    model_raw: str | None
    version_raw: str | None
    year_raw: int | None
    mileage_raw: Decimal | None
    image_url: str | None
    attributes_json: dict
    observed_at: datetime


def _extract_listing_id_from_url(url: str) -> str | None:
    match = re.search(r"/(MCO-\d+)-|/(MCO\d+)-", url)
    if not match:
        return None
    return (match.group(1) or match.group(2) or "").replace("-", "")


def _parse_price(value: str | None) -> Decimal | None:
    if not value:
        return None
    numeric = value.replace(".", "").replace(",", "").strip()
    if not numeric.isdigit():
        return None
    return Decimal(numeric)


def _parse_year_and_mileage(items: list[str]) -> tuple[int | None, Decimal | None]:
    year_raw: int | None = None
    mileage_raw: Decimal | None = None

    for item in items:
        normalized = item.strip()
        if re.fullmatch(r"(19|20)\d{2}", normalized):
            year_raw = int(normalized)
        if "km" in normalized.lower():
            digits = re.sub(r"[^0-9]", "", normalized)
            if digits:
                mileage_raw = Decimal(digits)

    return year_raw, mileage_raw


def _parse_location(location_raw: str | None) -> tuple[str | None, str | None]:
    if not location_raw:
        return None, None
    parts = [part.strip() for part in location_raw.split("-")]
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def _infer_brand_model_version(title: str | None) -> tuple[str | None, str | None, str | None]:
    if not title:
        return None, None, None

    tokens = title.split()
    brand = tokens[0] if tokens else None
    model = tokens[1] if len(tokens) > 1 else None
    version = " ".join(tokens[2:]) if len(tokens) > 2 else None
    return brand, model, version


def _parse_cards_from_html(html: str) -> list[SearchCardRecord]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[SearchCardRecord] = []

    for item in soup.select("li.ui-search-layout__item"):
        anchor = item.select_one("a.poly-component__title")
        if not anchor:
            continue

        source_url = anchor.get("href", "").strip()
        source_listing_id = _extract_listing_id_from_url(source_url)
        if not source_listing_id:
            continue

        title_raw = anchor.get_text(strip=True) or None
        price_fraction = item.select_one("span.andes-money-amount__fraction")
        price_amount = _parse_price(price_fraction.get_text(strip=True) if price_fraction else None)

        location_node = item.select_one("span.poly-component__location")
        location_raw = location_node.get_text(strip=True) if location_node else None
        city_raw, state_raw = _parse_location(location_raw)

        attr_values = [
            node.get_text(" ", strip=True)
            for node in item.select("ul.poly-attributes_list li.poly-attributes_list__item")
        ]
        year_raw, mileage_raw = _parse_year_and_mileage(attr_values)
        brand_raw, model_raw, version_raw = _infer_brand_model_version(title_raw)

        image_node = item.select_one("img.poly-component__picture")
        image_url = image_node.get("src") if image_node else None

        records.append(
            SearchCardRecord(
                source_listing_id=source_listing_id,
                source_url=source_url,
                title_raw=title_raw,
                price_amount=price_amount,
                location_raw=location_raw,
                city_raw=city_raw,
                state_raw=state_raw,
                brand_raw=brand_raw,
                model_raw=model_raw,
                version_raw=version_raw,
                year_raw=year_raw,
                mileage_raw=mileage_raw,
                image_url=image_url,
                attributes_json={"search_card_attributes": attr_values},
                observed_at=datetime.now(timezone.utc),
            )
        )

    return records


def process_raw_to_staging(extract_run_id: str | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    with SessionLocal() as db:
        query = db.query(ExtractRunModel).order_by(ExtractRunModel.started_at.desc())
        if extract_run_id:
            query = query.filter(ExtractRunModel.id == extract_run_id)

        extract_run = query.first()
        if not extract_run:
            LOGGER.warning("No extract run found to process.")
            return

        notes = extract_run.notes or ""
        search_html_match = re.search(r"search_html=([^;]+)", notes)
        if not search_html_match:
            LOGGER.warning("Extract run %s does not contain search_html path.", extract_run.id)
            return

        html_path = Path(search_html_match.group(1).strip())
        if not html_path.exists():
            LOGGER.warning("Search HTML path does not exist: %s", html_path)
            return

        html = html_path.read_text(encoding="utf-8")
        records = _parse_cards_from_html(html)

        deleted_count = (
            db.query(StagingMarketplaceListingModel)
            .filter(StagingMarketplaceListingModel.extract_run_id == str(extract_run.id))
            .delete()
        )
        if deleted_count:
            LOGGER.info("Deleted %s previous staging rows for extract run %s.", deleted_count, extract_run.id)

        for record in records:
            db.add(
                StagingMarketplaceListingModel(
                    extract_run_id=str(extract_run.id),
                    source_listing_id=record.source_listing_id,
                    source_url=record.source_url,
                    title_raw=record.title_raw,
                    description_raw=None,
                    price_amount=record.price_amount,
                    currency="COP",
                    location_raw=record.location_raw,
                    city_raw=record.city_raw,
                    state_raw=record.state_raw,
                    brand_raw=record.brand_raw,
                    model_raw=record.model_raw,
                    version_raw=record.version_raw,
                    year_raw=record.year_raw,
                    mileage_raw=record.mileage_raw,
                    fuel_raw=None,
                    transmission_raw=None,
                    vehicle_type_raw="car",
                    color_raw=None,
                    attributes_json=record.attributes_json,
                    image_url=record.image_url,
                    search_query=(extract_run.query_params or {}).get("query"),
                    observed_at=record.observed_at,
                )
            )

        db.commit()

    LOGGER.info("raw_to_staging completed with %s staging rows.", len(records))
