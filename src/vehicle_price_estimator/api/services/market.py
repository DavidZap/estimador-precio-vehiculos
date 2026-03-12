from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, cast, func, select
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlalchemy.orm import Session

from vehicle_price_estimator.api.schemas.market import (
    ComparableResponse,
    FilterOption,
    MarketDistributionResponse,
    MarketFiltersResponse,
    MarketListingItem,
    MarketListingsResponse,
    MarketSearchFilters,
    MarketSummaryResponse,
    PriceDistributionBucket,
)
from vehicle_price_estimator.infrastructure.db.models.staging_listing import (
    StagingMarketplaceListingModel,
)
from vehicle_price_estimator.infrastructure.db.models.vehicle import ListingModel


def _normalize_text(value: str | None) -> str | None:
    return value.strip().lower() if value else None


def _latest_listing_media_subquery():
    ranked_subquery = (
        select(
            StagingMarketplaceListingModel.source_listing_id.label("source_listing_id"),
            StagingMarketplaceListingModel.source_url.label("source_url"),
            StagingMarketplaceListingModel.image_url.label("image_url"),
            func.row_number()
            .over(
                partition_by=StagingMarketplaceListingModel.source_listing_id,
                order_by=StagingMarketplaceListingModel.observed_at.desc(),
            )
            .label("row_number"),
        )
        .subquery()
    )

    return (
        select(
            ranked_subquery.c.source_listing_id,
            ranked_subquery.c.source_url,
            ranked_subquery.c.image_url,
        )
        .where(ranked_subquery.c.row_number == 1)
        .subquery()
    )


def _apply_filters(stmt, filters: MarketSearchFilters):
    if filters.brand:
        stmt = stmt.where(func.lower(ListingModel.brand_std) == _normalize_text(filters.brand))
    if filters.model:
        stmt = stmt.where(func.lower(ListingModel.model_std) == _normalize_text(filters.model))
    if filters.trim:
        stmt = stmt.where(func.lower(ListingModel.trim_std) == _normalize_text(filters.trim))
    if filters.department:
        stmt = stmt.where(func.lower(ListingModel.department_std) == _normalize_text(filters.department))
    if filters.municipality:
        stmt = stmt.where(
            func.lower(ListingModel.municipality_std) == _normalize_text(filters.municipality),
        )
    if filters.locality:
        stmt = stmt.where(func.lower(ListingModel.locality_std) == _normalize_text(filters.locality))
    if filters.fuel_type:
        stmt = stmt.where(func.lower(ListingModel.fuel_type_std) == _normalize_text(filters.fuel_type))
    if filters.transmission:
        stmt = stmt.where(
            func.lower(ListingModel.transmission_std) == _normalize_text(filters.transmission),
        )
    if filters.year_min is not None:
        stmt = stmt.where(ListingModel.year >= filters.year_min)
    if filters.year_max is not None:
        stmt = stmt.where(ListingModel.year <= filters.year_max)
    if filters.mileage_min is not None:
        stmt = stmt.where(ListingModel.mileage_km >= filters.mileage_min)
    if filters.mileage_max is not None:
        stmt = stmt.where(ListingModel.mileage_km <= filters.mileage_max)
    if filters.price_min is not None:
        stmt = stmt.where(ListingModel.price_cop >= filters.price_min)
    if filters.price_max is not None:
        stmt = stmt.where(ListingModel.price_cop <= filters.price_max)
    if filters.hybrid_flag is not None:
        stmt = stmt.where(ListingModel.hybrid_flag.is_(filters.hybrid_flag))
    if filters.mhev_flag is not None:
        stmt = stmt.where(ListingModel.mhev_flag.is_(filters.mhev_flag))
    if filters.outlier_flag is not None:
        stmt = stmt.where(ListingModel.outlier_flag.is_(filters.outlier_flag))
    if filters.is_active is not None:
        stmt = stmt.where(ListingModel.is_active.is_(filters.is_active))
    return stmt


def _base_listing_stmt(filters: MarketSearchFilters):
    media_subquery = _latest_listing_media_subquery()
    stmt = (
        select(
            ListingModel.id,
            ListingModel.source_name,
            ListingModel.source_listing_id,
            media_subquery.c.source_url,
            media_subquery.c.image_url,
            ListingModel.title_clean,
            ListingModel.price_cop,
            ListingModel.year,
            ListingModel.mileage_km,
            ListingModel.brand_std,
            ListingModel.model_std,
            ListingModel.trim_std,
            ListingModel.version_std,
            ListingModel.engine_displacement_std,
            ListingModel.transmission_std,
            ListingModel.fuel_type_std,
            ListingModel.department_std,
            ListingModel.municipality_std,
            ListingModel.locality_std,
            ListingModel.city_std,
            ListingModel.latitude,
            ListingModel.longitude,
            ListingModel.outlier_flag,
            ListingModel.is_active,
            ListingModel.updated_at,
        )
        .select_from(ListingModel)
        .outerjoin(
            media_subquery,
            media_subquery.c.source_listing_id == ListingModel.source_listing_id,
        )
    )
    return _apply_filters(stmt, filters)


def _build_listing_item(row) -> MarketListingItem:
    return MarketListingItem.model_validate(dict(row._mapping))


def get_market_listings(
    db: Session,
    filters: MarketSearchFilters,
    page: int,
    page_size: int,
) -> MarketListingsResponse:
    base_stmt = _base_listing_stmt(filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    stmt = (
        base_stmt.order_by(
            ListingModel.price_cop.asc().nulls_last(),
            ListingModel.updated_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(stmt).all()

    return MarketListingsResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_build_listing_item(row) for row in rows],
    )


def _facet_options(
    db: Session,
    filters: MarketSearchFilters,
    column,
    *,
    limit: int = 25,
    descending: bool = False,
) -> list[FilterOption]:
    stmt = (
        select(column.label("value"), func.count().label("count"))
        .select_from(ListingModel)
        .where(column.is_not(None))
    )
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.group_by(column)

    if descending:
        stmt = stmt.order_by(column.desc())
    else:
        stmt = stmt.order_by(func.count().desc(), column.asc())

    rows = db.execute(stmt.limit(limit)).all()
    return [FilterOption(value=row.value, count=row.count) for row in rows]


def get_market_filters(db: Session, filters: MarketSearchFilters) -> MarketFiltersResponse:
    return MarketFiltersResponse(
        brands=_facet_options(db, filters, ListingModel.brand_std),
        models=_facet_options(db, filters, ListingModel.model_std),
        trims=_facet_options(db, filters, ListingModel.trim_std),
        departments=_facet_options(db, filters, ListingModel.department_std),
        municipalities=_facet_options(db, filters, ListingModel.municipality_std),
        localities=_facet_options(db, filters, ListingModel.locality_std),
        fuel_types=_facet_options(db, filters, ListingModel.fuel_type_std),
        transmissions=_facet_options(db, filters, ListingModel.transmission_std),
        years=_facet_options(db, filters, ListingModel.year, descending=True),
    )


def get_market_summary(db: Session, filters: MarketSearchFilters) -> MarketSummaryResponse:
    filtered_subquery = (
        _apply_filters(
            select(
                ListingModel.price_cop.label("price_cop"),
                ListingModel.mileage_km.label("mileage_km"),
                ListingModel.year.label("year"),
                ListingModel.outlier_flag.label("outlier_flag"),
                ListingModel.is_active.label("is_active"),
            ),
            filters,
        )
        .subquery()
    )

    stmt = select(
        func.count().label("total_listings"),
        func.sum(case((filtered_subquery.c.is_active.is_(True), 1), else_=0)).label("active_listings"),
        func.sum(case((filtered_subquery.c.outlier_flag.is_(True), 1), else_=0)).label("outlier_listings"),
        cast(func.avg(filtered_subquery.c.price_cop), NUMERIC(14, 2)).label("avg_price_cop"),
        cast(
            func.percentile_cont(0.5).within_group(filtered_subquery.c.price_cop),
            NUMERIC(14, 2),
        ).label("median_price_cop"),
        cast(func.min(filtered_subquery.c.price_cop), NUMERIC(14, 2)).label("min_price_cop"),
        cast(func.max(filtered_subquery.c.price_cop), NUMERIC(14, 2)).label("max_price_cop"),
        cast(func.avg(filtered_subquery.c.mileage_km), NUMERIC(14, 2)).label("avg_mileage_km"),
        func.min(filtered_subquery.c.year).label("min_year"),
        func.max(filtered_subquery.c.year).label("max_year"),
    )
    row = db.execute(stmt).one()
    return MarketSummaryResponse.model_validate(dict(row._mapping))


def get_market_distribution(
    db: Session,
    filters: MarketSearchFilters,
    bucket_count: int,
) -> MarketDistributionResponse:
    prices = [
        row[0]
        for row in db.execute(
            _apply_filters(
                select(ListingModel.price_cop).where(ListingModel.price_cop.is_not(None)),
                filters,
            ).order_by(ListingModel.price_cop.asc()),
        ).all()
        if row[0] is not None
    ]

    if not prices:
        return MarketDistributionResponse(total_listings=0, bucket_count=bucket_count, buckets=[])

    min_price = prices[0]
    max_price = prices[-1]
    if min_price == max_price:
        return MarketDistributionResponse(
            total_listings=len(prices),
            bucket_count=1,
            min_price_cop=min_price,
            max_price_cop=max_price,
            p10_price_cop=min_price,
            p25_price_cop=min_price,
            p50_price_cop=min_price,
            p75_price_cop=min_price,
            p90_price_cop=min_price,
            buckets=[PriceDistributionBucket(start_price_cop=min_price, end_price_cop=max_price, count=len(prices))],
        )

    bucket_count = max(1, bucket_count)
    step = (max_price - min_price) / Decimal(bucket_count)
    buckets: list[PriceDistributionBucket] = []

    for index in range(bucket_count):
        start = min_price + (step * index)
        end = max_price if index == bucket_count - 1 else min_price + (step * (index + 1))
        if index == bucket_count - 1:
            count = sum(1 for price in prices if start <= price <= end)
        else:
            count = sum(1 for price in prices if start <= price < end)
        buckets.append(
            PriceDistributionBucket(
                start_price_cop=start.quantize(Decimal("0.01")),
                end_price_cop=end.quantize(Decimal("0.01")),
                count=count,
            ),
        )

    def percentile(rank: float) -> Decimal:
        position = (len(prices) - 1) * rank
        lower = int(position)
        upper = min(lower + 1, len(prices) - 1)
        if lower == upper:
            return prices[lower]
        weight = Decimal(str(position - lower))
        return prices[lower] + ((prices[upper] - prices[lower]) * weight)

    return MarketDistributionResponse(
        total_listings=len(prices),
        bucket_count=bucket_count,
        min_price_cop=min_price,
        max_price_cop=max_price,
        p10_price_cop=percentile(0.10).quantize(Decimal("0.01")),
        p25_price_cop=percentile(0.25).quantize(Decimal("0.01")),
        p50_price_cop=percentile(0.50).quantize(Decimal("0.01")),
        p75_price_cop=percentile(0.75).quantize(Decimal("0.01")),
        p90_price_cop=percentile(0.90).quantize(Decimal("0.01")),
        buckets=buckets,
    )


def get_comparables(
    db: Session,
    filters: MarketSearchFilters,
    *,
    target_year: int | None,
    target_mileage_km: Decimal | None,
    target_price_cop: Decimal | None,
    limit: int,
) -> ComparableResponse:
    media_subquery = _latest_listing_media_subquery()
    stmt = (
        select(
            ListingModel.id,
            ListingModel.source_name,
            ListingModel.source_listing_id,
            media_subquery.c.source_url,
            media_subquery.c.image_url,
            ListingModel.title_clean,
            ListingModel.price_cop,
            ListingModel.year,
            ListingModel.mileage_km,
            ListingModel.brand_std,
            ListingModel.model_std,
            ListingModel.trim_std,
            ListingModel.version_std,
            ListingModel.engine_displacement_std,
            ListingModel.transmission_std,
            ListingModel.fuel_type_std,
            ListingModel.department_std,
            ListingModel.municipality_std,
            ListingModel.locality_std,
            ListingModel.city_std,
            ListingModel.latitude,
            ListingModel.longitude,
            ListingModel.outlier_flag,
            ListingModel.is_active,
            ListingModel.updated_at,
            (
                case((ListingModel.trim_std == filters.trim, 0), else_=1.5 if filters.trim else 0)
                + case(
                    (ListingModel.transmission_std == filters.transmission, 0),
                    else_=1.0 if filters.transmission else 0,
                )
                + case(
                    (ListingModel.fuel_type_std == filters.fuel_type, 0),
                    else_=1.0 if filters.fuel_type else 0,
                )
                + (
                    func.abs(func.coalesce(ListingModel.year, target_year or 0) - (target_year or 0))
                    / 2.0
                    if target_year is not None
                    else 0
                )
                + (
                    func.abs(
                        func.coalesce(cast(ListingModel.mileage_km, NUMERIC(14, 2)), target_mileage_km or 0)
                        - (target_mileage_km or 0)
                    )
                    / 20000.0
                    if target_mileage_km is not None
                    else 0
                )
                + (
                    func.abs(
                        func.coalesce(cast(ListingModel.price_cop, NUMERIC(14, 2)), target_price_cop or 0)
                        - (target_price_cop or 0)
                    )
                    / 10000000.0
                    if target_price_cop is not None
                    else 0
                )
            ).label("comparable_score"),
        )
        .select_from(ListingModel)
        .outerjoin(
            media_subquery,
            media_subquery.c.source_listing_id == ListingModel.source_listing_id,
        )
    )
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.where(ListingModel.price_cop.is_not(None))

    total_candidates = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by("comparable_score", ListingModel.updated_at.desc()).limit(limit)).all()

    items = []
    for row in rows:
        payload = dict(row._mapping)
        items.append(payload)

    return ComparableResponse(
        total_candidates=total_candidates,
        items=items,
    )
