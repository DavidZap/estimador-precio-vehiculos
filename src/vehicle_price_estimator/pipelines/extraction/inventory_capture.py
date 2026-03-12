from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.vehicle import ListingModel
from vehicle_price_estimator.infrastructure.db.session import SessionLocal
from vehicle_price_estimator.pipelines.extraction.run_extraction import run_extraction_pipeline


LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InventoryBrand:
    code: str
    display_name: str
    search_term: str


@dataclass(frozen=True, slots=True)
class InventoryRegion:
    code: str
    city: str
    department: str
    region_group: str
    search_term: str


@dataclass(frozen=True, slots=True)
class InventoryCaptureQuery:
    query: str
    brand_code: str
    region_code: str
    phase: str
    model_hint: str | None = None
    year_hint: int | None = None


DEFAULT_BRANDS = [
    InventoryBrand("toyota", "Toyota", "toyota"),
    InventoryBrand("mazda", "Mazda", "mazda"),
    InventoryBrand("chevrolet", "Chevrolet", "chevrolet"),
    InventoryBrand("volkswagen", "Volkswagen", "volkswagen"),
    InventoryBrand("renault", "Renault", "renault"),
    InventoryBrand("byd", "BYD", "byd"),
    InventoryBrand("kia", "Kia", "kia"),
    InventoryBrand("mercedes_benz", "Mercedes-Benz", "mercedes benz"),
    InventoryBrand("bmw", "BMW", "bmw"),
    InventoryBrand("audi", "Audi", "audi"),
    InventoryBrand("nissan", "Nissan", "nissan"),
]

DEFAULT_REGIONS = [
    InventoryRegion("bogota", "Bogota", "Bogota D.C.", "centro", "bogota"),
    InventoryRegion("medellin", "Medellin", "Antioquia", "noroccidente", "medellin"),
    InventoryRegion("cali", "Cali", "Valle del Cauca", "pacifico", "cali"),
    InventoryRegion("barranquilla", "Barranquilla", "Atlantico", "caribe", "barranquilla"),
    InventoryRegion("cartagena", "Cartagena", "Bolivar", "caribe", "cartagena"),
    InventoryRegion("bucaramanga", "Bucaramanga", "Santander", "oriente", "bucaramanga"),
    InventoryRegion("cucuta", "Cucuta", "Norte de Santander", "oriente", "cucuta"),
    InventoryRegion("pereira", "Pereira", "Risaralda", "eje_cafetero", "pereira"),
    InventoryRegion("villavicencio", "Villavicencio", "Meta", "llanos", "villavicencio"),
    InventoryRegion("pasto", "Pasto", "Narino", "sur", "pasto"),
]

DEFAULT_YEAR_ANCHORS = [2010, 2014, 2018, 2022, datetime.now().year]


def _deduplicate_queries(queries: list[InventoryCaptureQuery]) -> list[InventoryCaptureQuery]:
    seen: set[tuple[str, str, str, str | None, int | None]] = set()
    unique_queries: list[InventoryCaptureQuery] = []
    for query in queries:
        key = (
            query.query.lower(),
            query.brand_code,
            query.region_code,
            query.model_hint,
            query.year_hint,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_queries.append(query)
    return unique_queries


def get_inventory_brands(selected_codes: list[str] | None = None) -> list[InventoryBrand]:
    if not selected_codes:
        return DEFAULT_BRANDS
    selected = {code.strip().lower() for code in selected_codes if code.strip()}
    return [brand for brand in DEFAULT_BRANDS if brand.code in selected]


def get_inventory_regions(selected_codes: list[str] | None = None) -> list[InventoryRegion]:
    if not selected_codes:
        return DEFAULT_REGIONS
    selected = {code.strip().lower() for code in selected_codes if code.strip()}
    return [region for region in DEFAULT_REGIONS if region.code in selected]


def build_discovery_queries(
    brands: list[InventoryBrand],
    regions: list[InventoryRegion],
) -> list[InventoryCaptureQuery]:
    return _deduplicate_queries(
        [
            InventoryCaptureQuery(
                query=f"{brand.search_term} {region.search_term}",
                brand_code=brand.code,
                region_code=region.code,
                phase="discovery",
            )
            for brand in brands
            for region in regions
        ]
    )


def build_year_backfill_queries(
    brands: list[InventoryBrand],
    regions: list[InventoryRegion],
    year_anchors: list[int] | None = None,
) -> list[InventoryCaptureQuery]:
    anchors = year_anchors or DEFAULT_YEAR_ANCHORS
    return _deduplicate_queries(
        [
            InventoryCaptureQuery(
                query=f"{brand.search_term} {year} {region.search_term}",
                brand_code=brand.code,
                region_code=region.code,
                phase="year_backfill",
                year_hint=year,
            )
            for brand in brands
            for region in regions
            for year in anchors
        ]
    )


def build_model_region_queries(
    brands: list[InventoryBrand],
    regions: list[InventoryRegion],
    *,
    min_model_count: int = 2,
    max_models_per_brand: int = 12,
) -> list[InventoryCaptureQuery]:
    brand_map = {brand.display_name.lower(): brand for brand in brands}

    with SessionLocal() as db:
        rows = (
            db.query(
                ListingModel.brand_std,
                ListingModel.model_std,
                func.count(ListingModel.id).label("listing_count"),
            )
            .filter(
                ListingModel.brand_std.is_not(None),
                ListingModel.model_std.is_not(None),
                ListingModel.year.is_not(None),
                ListingModel.year >= 2010,
            )
            .group_by(ListingModel.brand_std, ListingModel.model_std)
            .having(func.count(ListingModel.id) >= min_model_count)
            .order_by(ListingModel.brand_std.asc(), func.count(ListingModel.id).desc())
            .all()
        )

    grouped: dict[str, list[str]] = {}
    for brand_std, model_std, _ in rows:
        if brand_std is None or model_std is None:
            continue
        brand_key = brand_std.lower()
        if brand_key not in brand_map:
            continue
        grouped.setdefault(brand_key, [])
        if model_std not in grouped[brand_key]:
            grouped[brand_key].append(model_std)

    queries: list[InventoryCaptureQuery] = []
    for brand in brands:
        models = grouped.get(brand.display_name.lower(), [])[:max_models_per_brand]
        for model in models:
            model_term = str(model).lower()
            for region in regions:
                queries.append(
                    InventoryCaptureQuery(
                        query=f"{brand.search_term} {model_term} {region.search_term}",
                        brand_code=brand.code,
                        region_code=region.code,
                        phase="model_region",
                        model_hint=str(model),
                    )
                )

    return _deduplicate_queries(queries)


def build_inventory_capture_plan(
    *,
    brands: list[InventoryBrand],
    regions: list[InventoryRegion],
    campaign: str,
    min_model_count: int = 2,
    max_models_per_brand: int = 12,
    year_anchors: list[int] | None = None,
) -> list[InventoryCaptureQuery]:
    if campaign == "discovery":
        return build_discovery_queries(brands, regions)
    if campaign == "year_backfill":
        return build_year_backfill_queries(brands, regions, year_anchors)
    if campaign == "model_region":
        return build_model_region_queries(
            brands,
            regions,
            min_model_count=min_model_count,
            max_models_per_brand=max_models_per_brand,
        )
    if campaign == "full":
        queries = build_discovery_queries(brands, regions)
        queries.extend(
            build_model_region_queries(
                brands,
                regions,
                min_model_count=min_model_count,
                max_models_per_brand=max_models_per_brand,
            )
        )
        queries.extend(build_year_backfill_queries(brands, regions, year_anchors))
        return _deduplicate_queries(queries)
    raise ValueError(f"Unsupported campaign: {campaign}")


def run_inventory_capture_campaign(
    *,
    campaign: str = "discovery",
    brand_codes: list[str] | None = None,
    region_codes: list[str] | None = None,
    limit: int = 48,
    fetch_item_details: bool = False,
    process_pipeline: bool = True,
    sleep_seconds: float = 1.0,
    dry_run: bool = False,
    max_queries: int | None = None,
    min_model_count: int = 2,
    max_models_per_brand: int = 12,
    year_anchors: list[int] | None = None,
) -> list[InventoryCaptureQuery]:
    settings = get_settings()
    configure_logging(settings.log_level)

    brands = get_inventory_brands(brand_codes)
    regions = get_inventory_regions(region_codes)
    plan = build_inventory_capture_plan(
        brands=brands,
        regions=regions,
        campaign=campaign,
        min_model_count=min_model_count,
        max_models_per_brand=max_models_per_brand,
        year_anchors=year_anchors,
    )

    if max_queries is not None:
        plan = plan[:max_queries]

    LOGGER.info(
        "Inventory capture plan built with %s queries for campaign '%s'.",
        len(plan),
        campaign,
    )

    if dry_run:
        return plan

    for index, capture_query in enumerate(plan, start=1):
        LOGGER.info(
            "[%s/%s] Running query '%s' (brand=%s region=%s phase=%s).",
            index,
            len(plan),
            capture_query.query,
            capture_query.brand_code,
            capture_query.region_code,
            capture_query.phase,
        )
        try:
            extract_run_id = run_extraction_pipeline(
                query=capture_query.query,
                limit=limit,
                fetch_item_details=fetch_item_details,
            )
            if process_pipeline:
                from vehicle_price_estimator.pipelines.processing.raw_to_staging import (
                    process_raw_to_staging,
                )
                from vehicle_price_estimator.pipelines.processing.staging_to_core import (
                    process_staging_to_core,
                )

                process_raw_to_staging(extract_run_id=extract_run_id)
                process_staging_to_core(extract_run_id=extract_run_id)
        except Exception as exc:
            LOGGER.exception("Inventory capture failed for query '%s': %s", capture_query.query, exc)

        if sleep_seconds > 0 and index < len(plan):
            time.sleep(sleep_seconds)

    return plan
