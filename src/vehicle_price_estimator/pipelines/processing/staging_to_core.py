from __future__ import annotations

import re
import uuid
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from statistics import quantiles
from uuid import UUID

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.db.models.listing_feature import ListingFeatureModel
from vehicle_price_estimator.infrastructure.db.models.location_reference import (
    ColombiaLocationReferenceModel,
)
from vehicle_price_estimator.infrastructure.db.models.listing_status_history import (
    ListingStatusHistoryModel,
)
from vehicle_price_estimator.infrastructure.db.models.price_history import ListingPriceHistoryModel
from vehicle_price_estimator.infrastructure.db.models.staging_listing import (
    StagingMarketplaceListingModel,
)
from vehicle_price_estimator.infrastructure.db.models.vehicle import ListingModel, VehicleCanonicalModel
from vehicle_price_estimator.infrastructure.db.session import SessionLocal


LOGGER = get_logger(__name__)
CURRENT_YEAR = datetime.now(UTC).year
EQUIPMENT_KEYWORDS = {
    "touring": Decimal("0.25"),
    "grand touring": Decimal("0.40"),
    "carbon": Decimal("0.20"),
    "hibrido": Decimal("0.35"),
    "hybrid": Decimal("0.35"),
    "sport": Decimal("0.20"),
    "lx": Decimal("0.15"),
    "at": Decimal("0.10"),
    "mt": Decimal("0.05"),
}
TRIM_PATTERNS = [
    "grand touring",
    "sport touring",
    "carbon edition",
    "touring",
    "prime",
    "sport",
    "signature",
    "exclusive",
    "lx",
    "gt",
]
MARKETING_PATTERNS = [
    "all new",
    "carbon edition",
    "signature",
    "plus",
]
COMPOUND_MODEL_PATTERNS: dict[str, list[str]] = {
    "Toyota": [
        "corolla cross",
        "land cruiser",
        "prado txl",
        "prado tz",
        "hilux sw4",
    ],
    "Mazda": [
        "cx-3",
        "cx-30",
        "cx-5",
        "cx-50",
        "bt-50",
    ],
    "Chevrolet": [
        "captiva xl",
        "tracker turbo",
        "onix turbo",
    ],
    "Volkswagen": [
        "gol trend",
        "nivus",
        "t-cross",
        "taos",
        "saveiro cross",
    ],
    "Renault": [
        "logan intens",
        "sandero stepway",
        "stepway zen",
        "duster oroch",
    ],
    "Byd": [
        "song plus",
        "yuan plus",
        "seal u",
        "seagull",
    ],
    "Kia": [
        "picanto ion",
        "sonet",
        "sportage revolution",
    ],
    "Mercedes-Benz": [
        "a 200",
        "c 200",
        "gla 200",
        "glc 300",
        "cla 200",
    ],
    "BMW": [
        "serie 1",
        "serie 2",
        "serie 3",
        "serie 4",
        "x1",
        "x3",
        "x5",
    ],
    "Audi": [
        "a3 sedan",
        "a4 allroad",
        "q3 sportback",
        "q5 sportback",
    ],
    "Nissan": [
        "x-trail",
        "qashqai",
        "versa sense",
        "kicks advance",
    ],
}
BOGOTA_LOCALITIES = {
    "Usaquen",
    "Chapinero",
    "Santa Fe",
    "San Cristobal",
    "Usme",
    "Tunjuelito",
    "Bosa",
    "Kennedy",
    "Fontibon",
    "Engativa",
    "Suba",
    "Barrios Unidos",
    "Teusaquillo",
    "Los Martires",
    "Antonio Narino",
    "Puente Aranda",
    "La Candelaria",
    "Rafael Uribe Uribe",
    "Ciudad Bolivar",
    "Sumapaz",
    "Martires",
}


@dataclass(slots=True)
class NormalizedListing:
    source_listing_id: str
    source_name: str
    source_url: str
    title_clean: str | None
    price_amount: Decimal | None
    price_cop: Decimal | None
    currency: str
    city_std: str | None
    state_std: str | None
    brand_std: str | None
    model_std: str | None
    version_std: str | None
    trim_std: str | None
    year: int | None
    mileage_km: Decimal | None
    fuel_type_std: str | None
    transmission_std: str | None
    engine_displacement_std: str | None
    engine_cc: int | None
    hybrid_flag: bool
    mhev_flag: bool
    variant_raw: str | None
    marketing_tokens: list[str]
    vehicle_type_std: str | None
    color_std: str | None
    quality_score: Decimal
    listing_fingerprint: str
    observed_at: datetime
    extract_run_id: UUID | None
    raw_attributes: dict | None


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_spaces(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip()


def _title_case(value: str | None) -> str | None:
    normalized = _normalize_spaces(value)
    return normalized.title() if normalized else None


def _normalize_city_state(city_raw: str | None, state_raw: str | None) -> tuple[str | None, str | None]:
    city = _title_case(city_raw)
    state = _title_case(state_raw)
    if state:
        state = state.replace("D.C.", "D.C.").replace("Dc", "D.C.")
    return city, state


def _normalize_brand(value: str | None) -> str | None:
    value = _title_case(value)
    if not value:
        return None
    synonyms = {
        "Bmw": "BMW",
        "Mg": "MG",
        "Gmc": "GMC",
    }
    return synonyms.get(value, value)


def _normalize_model(value: str | None) -> str | None:
    return _title_case(value)


def _normalize_geo_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _title_case(_strip_accents(value))
    if not normalized:
        return None
    normalized = normalized.replace(",", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.replace(" D C", " D.C.")
    return normalized


def _resolve_geo_hierarchy(city_std: str | None, department_std: str | None) -> tuple[str | None, str | None]:
    normalized_city = _normalize_geo_name(city_std)
    normalized_department = _normalize_geo_name(department_std)

    if normalized_department == "Bogota D.C." and normalized_city in BOGOTA_LOCALITIES:
        return "Bogota D.C.", normalized_city

    return normalized_city, None


def _normalize_version(value: str | None) -> str | None:
    value = _normalize_spaces(value)
    return value.title() if value else None


def _match_compound_model(brand: str | None, title: str | None) -> str | None:
    title_clean = _normalize_spaces(_strip_accents(title or ""))
    if not title_clean:
        return None

    normalized_title = title_clean.lower()
    if brand:
        for pattern in COMPOUND_MODEL_PATTERNS.get(brand, []):
            pattern_normalized = _normalize_spaces(_strip_accents(pattern)) or pattern
            pattern_normalized = pattern_normalized.lower()
            if re.search(rf"\b{re.escape(pattern_normalized)}\b", normalized_title):
                return _title_case(pattern_normalized)

    generic_patterns = [
        "corolla cross",
        "sandero stepway",
        "duster oroch",
        "q3 sportback",
        "q5 sportback",
        "song plus",
        "yuan plus",
        "x-trail",
    ]
    for pattern in generic_patterns:
        if re.search(rf"\b{re.escape(pattern)}\b", normalized_title):
            return _title_case(pattern)

    return None


def _extract_model_from_title(brand: str | None, title: str | None, fallback_model: str | None) -> str | None:
    title_clean = _normalize_spaces(title)
    if not title_clean:
        return _normalize_model(fallback_model)

    compound_model = _match_compound_model(brand, title_clean)
    if compound_model:
        return compound_model

    tokens = title_clean.split()
    brand_token = (brand or "").lower()
    while tokens and tokens[0].lower() == brand_token:
        tokens.pop(0)

    if tokens:
        return _normalize_model(tokens[0])

    return _normalize_model(fallback_model)


def _remove_model_prefix(title: str | None, brand: str | None, model: str | None) -> str:
    value = _normalize_spaces(title) or ""
    if not value:
        return ""

    normalized_value = _normalize_spaces(_strip_accents(value)) or ""
    working_value = normalized_value

    if brand:
        brand_pattern = _normalize_spaces(_strip_accents(brand)) or brand
        working_value = re.sub(
            rf"^\s*{re.escape(brand_pattern)}\b\s*",
            "",
            working_value,
            flags=re.IGNORECASE,
        )

    if model:
        model_pattern = _normalize_spaces(_strip_accents(model)) or model
        working_value = re.sub(
            rf"^\s*{re.escape(model_pattern)}\b\s*",
            "",
            working_value,
            flags=re.IGNORECASE,
        )

    return _normalize_spaces(working_value) or ""


def _extract_engine_specs(text: str) -> tuple[str | None, int | None]:
    displacement = None
    engine_cc = None

    displacement_match = re.search(r"\b(\d\.\d)\b", text)
    if displacement_match:
        displacement = displacement_match.group(1)

    cc_match = re.search(r"\b(\d{3,4})\s*cc\b", text, flags=re.IGNORECASE)
    if cc_match:
        engine_cc = int(cc_match.group(1))
        if displacement is None and len(cc_match.group(1)) == 4:
            displacement = f"{cc_match.group(1)[0]}.{cc_match.group(1)[1]}"

    return displacement, engine_cc


def _extract_transmission_signal(text: str) -> str | None:
    haystack = _strip_accents(text.lower())
    if re.search(r"\b(at|aut|automatica|automatico)\b", haystack):
        return "Automatica"
    if re.search(r"\b(mt|mecanico|manual)\b", haystack):
        return "Manual"
    return None


def _extract_fuel_flags(text: str) -> tuple[str | None, bool, bool]:
    haystack = _strip_accents(text.lower())
    hybrid_flag = any(token in haystack for token in ["hibrido", "hybrid", "hev"])
    mhev_flag = "mhev" in haystack or "hibrido ligero" in haystack

    if "diesel" in haystack:
        return "Diesel", hybrid_flag, mhev_flag
    if "electr" in haystack:
        return "Electrico", hybrid_flag, mhev_flag
    if hybrid_flag:
        return "Hibrido", hybrid_flag, mhev_flag
    if haystack:
        return "Gasolina", hybrid_flag, mhev_flag
    return None, hybrid_flag, mhev_flag


def _extract_trim_and_variant(text: str) -> tuple[str | None, str | None, list[str]]:
    haystack = _strip_accents(text.lower())
    trim_tokens: list[str] = []
    marketing_tokens: list[str] = []
    residual = haystack

    for pattern in TRIM_PATTERNS:
        if pattern in residual:
            trim_tokens.append(pattern.title())
            residual = residual.replace(pattern, " ")

    for pattern in MARKETING_PATTERNS:
        if pattern in haystack:
            marketing_tokens.append(pattern.title())

    residual = re.sub(r"\b\d\.\d\b", " ", residual)
    residual = re.sub(r"\b\d{3,4}\s*cc\b", " ", residual)
    residual = re.sub(
        r"\b(at|mt|aut|automatica|automatico|manual|mecanico|hibrido|ligero|mhev|hybrid|hev)\b",
        " ",
        residual,
    )
    residual = re.sub(r"\s+", " ", residual).strip(" -")
    residual_tokens = []
    for token in residual.split():
        if not residual_tokens or residual_tokens[-1] != token:
            residual_tokens.append(token)
    residual = " ".join(residual_tokens)

    trim_std = " / ".join(dict.fromkeys(trim_tokens)) or None
    variant_raw = residual.title() if residual else None
    return trim_std, variant_raw, list(dict.fromkeys(marketing_tokens))


def _infer_transmission(title: str | None, version: str | None) -> str | None:
    haystack = " ".join(filter(None, [title, version])).lower()
    if " at" in f" {haystack}" or "automatic" in haystack or "automatica" in haystack:
        return "Automatica"
    if " mt" in f" {haystack}" or "manual" in haystack:
        return "Manual"
    return None


def _infer_fuel(title: str | None, version: str | None) -> str | None:
    haystack = _strip_accents(" ".join(filter(None, [title, version])).lower())
    if "hibrid" in haystack or "hybrid" in haystack:
        return "Hibrido"
    if "diesel" in haystack:
        return "Diesel"
    if "electr" in haystack:
        return "Electrico"
    if haystack:
        return "Gasolina"
    return None


def _build_listing_fingerprint(brand: str | None, model: str | None, year: int | None, mileage: Decimal | None, city: str | None) -> str:
    mileage_bucket = None
    if mileage is not None:
        mileage_bucket = int(mileage // Decimal("5000")) * 5000
    parts = [
        (brand or "").lower(),
        (model or "").lower(),
        str(year or ""),
        str(mileage_bucket or ""),
        (city or "").lower(),
    ]
    return "|".join(parts)


def _compute_quality_score(record: StagingMarketplaceListingModel) -> Decimal:
    filled = 0
    total = 7
    values = [
        record.title_raw,
        record.price_amount,
        record.location_raw,
        record.year_raw,
        record.mileage_raw,
        record.image_url,
        record.source_url,
    ]
    for value in values:
        if value is not None and value != "":
            filled += 1
    return (Decimal(filled) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))


def _compute_equipment_score(title: str | None, version: str | None) -> Decimal:
    haystack = _strip_accents(" ".join(filter(None, [title, version])).lower())
    score = Decimal("0")
    for keyword, weight in EQUIPMENT_KEYWORDS.items():
        if keyword in haystack:
            score += weight
    return min(score, Decimal("1.0"))


def _compute_iqr_bounds(prices: list[Decimal]) -> tuple[Decimal | None, Decimal | None]:
    if len(prices) < 4:
        return None, None
    ordered = sorted(float(price) for price in prices)
    q1, _, q3 = quantiles(ordered, n=4, method="inclusive")
    iqr = q3 - q1
    return Decimal(str(q1 - 1.5 * iqr)), Decimal(str(q3 + 1.5 * iqr))


def _normalize_staging_record(record: StagingMarketplaceListingModel) -> NormalizedListing:
    city_std, state_std = _normalize_city_state(record.city_raw, record.state_raw)
    brand_std = _normalize_brand(record.brand_raw)
    title_clean = _title_case(record.title_raw)
    model_std = _extract_model_from_title(brand_std, title_clean, record.model_raw)
    variant_source = " ".join(
        part for part in [_remove_model_prefix(title_clean, brand_std, model_std), record.version_raw or ""] if part
    ).strip()
    engine_displacement_std, engine_cc = _extract_engine_specs(variant_source)
    transmission_std = _extract_transmission_signal(variant_source) or _infer_transmission(
        title_clean,
        record.version_raw,
    )
    fuel_type_std, hybrid_flag, mhev_flag = _extract_fuel_flags(variant_source)
    trim_std, variant_raw, marketing_tokens = _extract_trim_and_variant(variant_source)
    version_std = _normalize_version(
        " ".join(
            part
            for part in [engine_displacement_std, trim_std, variant_raw]
            if part
        )
    )
    price_cop = record.price_amount if record.currency in (None, "", "COP") else None
    quality_score = _compute_quality_score(record)
    year_value = record.year_raw
    if year_value and year_value > CURRENT_YEAR + 1:
        year_value = None
    fingerprint = _build_listing_fingerprint(
        brand_std,
        model_std,
        year_value,
        record.mileage_raw,
        city_std,
    )

    extract_run_id = None
    try:
        extract_run_id = UUID(str(record.extract_run_id))
    except ValueError:
        extract_run_id = None

    return NormalizedListing(
        source_listing_id=record.source_listing_id,
        source_name=record.source_name,
        source_url=record.source_url,
        title_clean=title_clean,
        price_amount=record.price_amount,
        price_cop=price_cop,
        currency=record.currency or "COP",
        city_std=city_std,
        state_std=state_std,
        brand_std=brand_std,
        model_std=model_std,
        version_std=version_std,
        trim_std=trim_std,
        year=year_value,
        mileage_km=record.mileage_raw,
        fuel_type_std=fuel_type_std,
        transmission_std=transmission_std,
        engine_displacement_std=engine_displacement_std,
        engine_cc=engine_cc,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        variant_raw=variant_raw,
        marketing_tokens=marketing_tokens,
        vehicle_type_std=_title_case(record.vehicle_type_raw) or "Car",
        color_std=_title_case(record.color_raw),
        quality_score=quality_score,
        listing_fingerprint=fingerprint,
        observed_at=record.observed_at,
        extract_run_id=extract_run_id,
        raw_attributes=record.attributes_json,
    )


def process_staging_to_core(extract_run_id: str | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    with SessionLocal() as db:
        query = db.query(StagingMarketplaceListingModel)
        if extract_run_id:
            query = query.filter(StagingMarketplaceListingModel.extract_run_id == extract_run_id)
        else:
            latest_run_id = (
                db.query(StagingMarketplaceListingModel.extract_run_id)
                .order_by(StagingMarketplaceListingModel.created_at.desc())
                .limit(1)
                .scalar()
            )
            if latest_run_id:
                query = query.filter(StagingMarketplaceListingModel.extract_run_id == latest_run_id)

        staging_rows = query.order_by(StagingMarketplaceListingModel.id.asc()).all()
        if not staging_rows:
            LOGGER.warning("No staging rows found to process.")
            return

        normalized_rows = [_normalize_staging_record(row) for row in staging_rows]
        canonical_keys = []
        for row in normalized_rows:
            canonical_keys.append(
                "|".join(
                    [
                        (row.brand_std or "").lower(),
                        (row.model_std or "").lower(),
                        (row.trim_std or "").lower(),
                        (row.engine_displacement_std or "").lower(),
                        str(row.year or ""),
                        (row.fuel_type_std or "").lower(),
                        (row.transmission_std or "").lower(),
                        "hybrid" if row.hybrid_flag else "",
                        "mhev" if row.mhev_flag else "",
                    ]
                )
            )
        listing_keys = {(row.source_name, row.source_listing_id) for row in normalized_rows}
        version_counter = Counter(row.version_std or "unknown" for row in normalized_rows)
        region_counter = Counter((row.city_std or "unknown") for row in normalized_rows)
        inventory_counter = Counter(
            (row.brand_std or "unknown", row.model_std or "unknown", row.year or 0) for row in normalized_rows
        )

        prices_by_segment: dict[tuple[str, str, int], list[Decimal]] = defaultdict(list)
        for row in normalized_rows:
            if row.price_cop is None or row.brand_std is None or row.model_std is None or row.year is None:
                continue
            prices_by_segment[(row.brand_std, row.model_std, row.year)].append(row.price_cop)

        outlier_bounds = {
            segment: _compute_iqr_bounds(prices)
            for segment, prices in prices_by_segment.items()
        }

        existing_vehicles = (
            db.query(VehicleCanonicalModel)
            .filter(VehicleCanonicalModel.canonical_key.in_(canonical_keys))
            .all()
            if canonical_keys
            else []
        )
        vehicles_by_key = {vehicle.canonical_key: vehicle for vehicle in existing_vehicles}
        geo_reference = {
            (_normalize_geo_name(row.department_name_std), _normalize_geo_name(row.city_name_std)): row
            for row in db.query(ColombiaLocationReferenceModel).all()
        }

        for row, canonical_key in zip(normalized_rows, canonical_keys, strict=False):
            vehicle = vehicles_by_key.get(canonical_key)
            if vehicle is None:
                vehicle = VehicleCanonicalModel(
                    id=uuid.uuid4(),
                    brand_std=row.brand_std or "Unknown",
                    model_std=row.model_std or "Unknown",
                    version_std=row.version_std,
                    trim_std=row.trim_std,
                    body_type_std=row.vehicle_type_std,
                    fuel_type_std=row.fuel_type_std,
                    transmission_std=row.transmission_std,
                    engine_displacement_std=row.engine_displacement_std,
                    engine_cc=row.engine_cc,
                    hybrid_flag=row.hybrid_flag,
                    mhev_flag=row.mhev_flag,
                    variant_raw=row.variant_raw,
                    marketing_tokens_json=row.marketing_tokens,
                    year=row.year,
                    canonical_key=canonical_key,
                )
                db.add(vehicle)
                vehicles_by_key[canonical_key] = vehicle

        db.flush()

        source_names = sorted({key[0] for key in listing_keys})
        source_listing_ids = sorted({key[1] for key in listing_keys})
        existing_listings = (
            db.query(ListingModel)
            .filter(
                ListingModel.source_name.in_(source_names),
                ListingModel.source_listing_id.in_(source_listing_ids),
            )
            .all()
            if listing_keys
            else []
        )
        listings_by_key = {
            (listing.source_name, listing.source_listing_id): listing for listing in existing_listings
        }

        existing_listing_ids = [listing.id for listing in existing_listings]
        existing_history_keys = set()
        existing_status_keys = set()
        existing_features: dict = {}
        if existing_listing_ids:
            existing_history_keys = {
                (history.listing_id, history.observed_at)
                for history in db.query(ListingPriceHistoryModel)
                .filter(ListingPriceHistoryModel.listing_id.in_(existing_listing_ids))
                .all()
            }
            existing_status_keys = {
                (status.listing_id, status.observed_at, status.status)
                for status in db.query(ListingStatusHistoryModel)
                .filter(ListingStatusHistoryModel.listing_id.in_(existing_listing_ids))
                .all()
            }
            existing_features = {
                feature.listing_id: feature
                for feature in db.query(ListingFeatureModel)
                .filter(ListingFeatureModel.listing_id.in_(existing_listing_ids))
                .all()
            }

        prepared_rows: list[tuple[NormalizedListing, ListingModel]] = []

        for row, canonical_key in zip(normalized_rows, canonical_keys, strict=False):
            vehicle = vehicles_by_key.get(canonical_key)
            if vehicle is not None:
                vehicle.version_std = row.version_std
                vehicle.trim_std = row.trim_std
                vehicle.fuel_type_std = row.fuel_type_std
                vehicle.transmission_std = row.transmission_std
                vehicle.engine_displacement_std = row.engine_displacement_std
                vehicle.engine_cc = row.engine_cc
                vehicle.hybrid_flag = row.hybrid_flag
                vehicle.mhev_flag = row.mhev_flag
                vehicle.variant_raw = row.variant_raw
                vehicle.marketing_tokens_json = row.marketing_tokens

            listing_key = (row.source_name, row.source_listing_id)
            listing = listings_by_key.get(listing_key)

            if listing is None:
                listing = ListingModel(
                    id=uuid.uuid4(),
                    source_name=row.source_name,
                    source_listing_id=row.source_listing_id,
                    listing_fingerprint=row.listing_fingerprint,
                    first_seen_at=row.observed_at,
                    created_at=row.observed_at,
                )
                db.add(listing)
                listings_by_key[listing_key] = listing

            listing.vehicle_canonical_id = vehicle.id
            listing.listing_fingerprint = row.listing_fingerprint
            listing.title_clean = row.title_clean
            listing.price_amount = row.price_amount
            listing.currency = row.currency
            listing.price_cop = row.price_cop
            listing.city_std = row.city_std
            listing.state_std = row.state_std
            listing.department_std = row.state_std
            municipality_std, locality_std = _resolve_geo_hierarchy(row.city_std, row.state_std)
            listing.municipality_std = municipality_std or row.city_std
            listing.locality_std = locality_std
            listing.brand_std = row.brand_std
            listing.model_std = row.model_std
            listing.version_std = row.version_std
            listing.trim_std = row.trim_std
            listing.year = row.year
            listing.mileage_km = row.mileage_km
            listing.fuel_type_std = row.fuel_type_std
            listing.transmission_std = row.transmission_std
            listing.engine_displacement_std = row.engine_displacement_std
            listing.engine_cc = row.engine_cc
            listing.hybrid_flag = row.hybrid_flag
            listing.mhev_flag = row.mhev_flag
            listing.variant_raw = row.variant_raw
            listing.marketing_tokens_json = row.marketing_tokens
            listing.vehicle_type_std = row.vehicle_type_std
            listing.color_std = row.color_std
            listing.last_seen_at = row.observed_at
            listing.is_active = True
            listing.quality_score = row.quality_score
            geo_city = municipality_std or row.city_std
            geo_key = (_normalize_geo_name(row.state_std), _normalize_geo_name(geo_city))
            geo_match = geo_reference.get(geo_key)
            if geo_match is not None:
                listing.municipality_code = geo_match.municipality_code
                listing.latitude = geo_match.latitude
                listing.longitude = geo_match.longitude

            outlier_flag = False
            if row.brand_std and row.model_std and row.year and row.price_cop is not None:
                lower_upper = outlier_bounds.get((row.brand_std, row.model_std, row.year))
                if lower_upper:
                    lower, upper = lower_upper
                    if lower is not None and upper is not None:
                        outlier_flag = row.price_cop < lower or row.price_cop > upper
            listing.outlier_flag = outlier_flag

            prepared_rows.append((row, listing))

        db.flush()

        for row, listing in prepared_rows:
            history_key = (listing.id, row.observed_at)
            if history_key not in existing_history_keys and row.price_amount is not None and row.price_cop is not None:
                db.add(
                    ListingPriceHistoryModel(
                        listing_id=listing.id,
                        observed_at=row.observed_at,
                        price_amount=row.price_amount,
                        currency=row.currency,
                        price_cop=row.price_cop,
                        status="active",
                        extract_run_id=row.extract_run_id,
                    )
                )
                existing_history_keys.add(history_key)

            status_key = (listing.id, row.observed_at, "active")
            if status_key not in existing_status_keys:
                db.add(
                    ListingStatusHistoryModel(
                        listing_id=listing.id,
                        observed_at=row.observed_at,
                        status="active",
                        extract_run_id=row.extract_run_id,
                    )
                )
                existing_status_keys.add(status_key)

            vehicle_age = None
            km_per_year = None
            if row.year:
                vehicle_age = Decimal(max(CURRENT_YEAR - row.year, 0))
                if row.mileage_km is not None and vehicle_age > 0:
                    km_per_year = (row.mileage_km / vehicle_age).quantize(Decimal("0.01"))

            version_count = version_counter[row.version_std or "unknown"]
            total_versions = max(len(normalized_rows), 1)
            version_rarity_score = (Decimal("1") - (Decimal(version_count) / Decimal(total_versions))).quantize(
                Decimal("0.0001")
            )

            region_count = region_counter[row.city_std or "unknown"]
            regional_market_score = (Decimal(region_count) / Decimal(total_versions)).quantize(Decimal("0.0001"))

            comparable_inventory_density = Decimal(
                inventory_counter[(row.brand_std or "unknown", row.model_std or "unknown", row.year or 0)]
            )

            equipment_score = _compute_equipment_score(row.title_clean, row.version_std).quantize(
                Decimal("0.0001")
            )

            feature = existing_features.get(listing.id)
            if feature is None:
                feature = ListingFeatureModel(listing_id=listing.id, snapshot_date=row.observed_at.date())
                db.add(feature)
                existing_features[listing.id] = feature

            feature.snapshot_date = row.observed_at.date()
            feature.vehicle_age = vehicle_age
            feature.km_per_year = km_per_year
            feature.equipment_score = equipment_score
            feature.version_rarity_score = version_rarity_score
            feature.regional_market_score = regional_market_score
            feature.listing_age_days = Decimal(
                max((row.observed_at.date() - listing.first_seen_at.date()).days, 0)
            ).quantize(Decimal("0.00"))
            feature.comparable_inventory_density = comparable_inventory_density
            feature.text_flags_json = {
                "has_turbo": "turbo" in _strip_accents((row.title_clean or "").lower()),
                "has_hybrid": row.hybrid_flag,
                "has_mhev": row.mhev_flag,
            }
            feature.feature_payload = {
                "raw_attributes": row.raw_attributes or {},
                "listing_fingerprint": row.listing_fingerprint,
                "outlier_flag": outlier_flag,
                "trim_std": row.trim_std,
                "engine_displacement_std": row.engine_displacement_std,
                "engine_cc": row.engine_cc,
                "variant_raw": row.variant_raw,
                "marketing_tokens": row.marketing_tokens,
            }

        db.commit()

    LOGGER.info("staging_to_core completed with %s normalized listings.", len(normalized_rows))
