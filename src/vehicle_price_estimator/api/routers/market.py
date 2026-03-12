from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vehicle_price_estimator.api.deps import get_db
from vehicle_price_estimator.api.schemas.market import (
    ComparableResponse,
    MarketDistributionResponse,
    MarketFiltersResponse,
    MarketListingsResponse,
    MarketSearchFilters,
    MarketSummaryResponse,
)
from vehicle_price_estimator.api.services.market import (
    get_comparables,
    get_market_distribution,
    get_market_filters,
    get_market_listings,
    get_market_summary,
)


router = APIRouter(prefix="/market", tags=["market"])


def _build_filters(
    brand: str | None = None,
    model: str | None = None,
    trim: str | None = None,
    department: str | None = None,
    municipality: str | None = None,
    locality: str | None = None,
    fuel_type: str | None = None,
    transmission: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    mileage_min: Decimal | None = None,
    mileage_max: Decimal | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    hybrid_flag: bool | None = None,
    mhev_flag: bool | None = None,
    outlier_flag: bool | None = None,
    is_active: bool | None = True,
) -> MarketSearchFilters:
    return MarketSearchFilters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        year_min=year_min,
        year_max=year_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        price_min=price_min,
        price_max=price_max,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )


@router.get("/listings", response_model=MarketListingsResponse)
def list_market_inventory(
    brand: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    department: str | None = Query(default=None),
    municipality: str | None = Query(default=None),
    locality: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    year_min: int | None = Query(default=None, ge=1950, le=2100),
    year_max: int | None = Query(default=None, ge=1950, le=2100),
    mileage_min: Decimal | None = Query(default=None, ge=0),
    mileage_max: Decimal | None = Query(default=None, ge=0),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    hybrid_flag: bool | None = Query(default=None),
    mhev_flag: bool | None = Query(default=None),
    outlier_flag: bool | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MarketListingsResponse:
    filters = _build_filters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        year_min=year_min,
        year_max=year_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        price_min=price_min,
        price_max=price_max,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )
    return get_market_listings(db, filters, page=page, page_size=page_size)


@router.get("/filters", response_model=MarketFiltersResponse)
def list_market_filters(
    brand: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    department: str | None = Query(default=None),
    municipality: str | None = Query(default=None),
    locality: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    year_min: int | None = Query(default=None, ge=1950, le=2100),
    year_max: int | None = Query(default=None, ge=1950, le=2100),
    mileage_min: Decimal | None = Query(default=None, ge=0),
    mileage_max: Decimal | None = Query(default=None, ge=0),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    hybrid_flag: bool | None = Query(default=None),
    mhev_flag: bool | None = Query(default=None),
    outlier_flag: bool | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
) -> MarketFiltersResponse:
    filters = _build_filters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        year_min=year_min,
        year_max=year_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        price_min=price_min,
        price_max=price_max,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )
    return get_market_filters(db, filters)


@router.get("/summary", response_model=MarketSummaryResponse)
def get_inventory_summary(
    brand: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    department: str | None = Query(default=None),
    municipality: str | None = Query(default=None),
    locality: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    year_min: int | None = Query(default=None, ge=1950, le=2100),
    year_max: int | None = Query(default=None, ge=1950, le=2100),
    mileage_min: Decimal | None = Query(default=None, ge=0),
    mileage_max: Decimal | None = Query(default=None, ge=0),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    hybrid_flag: bool | None = Query(default=None),
    mhev_flag: bool | None = Query(default=None),
    outlier_flag: bool | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    db: Session = Depends(get_db),
) -> MarketSummaryResponse:
    filters = _build_filters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        year_min=year_min,
        year_max=year_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        price_min=price_min,
        price_max=price_max,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )
    return get_market_summary(db, filters)


@router.get("/distribution", response_model=MarketDistributionResponse)
def get_price_distribution(
    brand: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    department: str | None = Query(default=None),
    municipality: str | None = Query(default=None),
    locality: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    year_min: int | None = Query(default=None, ge=1950, le=2100),
    year_max: int | None = Query(default=None, ge=1950, le=2100),
    mileage_min: Decimal | None = Query(default=None, ge=0),
    mileage_max: Decimal | None = Query(default=None, ge=0),
    price_min: Decimal | None = Query(default=None, ge=0),
    price_max: Decimal | None = Query(default=None, ge=0),
    hybrid_flag: bool | None = Query(default=None),
    mhev_flag: bool | None = Query(default=None),
    outlier_flag: bool | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    bucket_count: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> MarketDistributionResponse:
    filters = _build_filters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        year_min=year_min,
        year_max=year_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        price_min=price_min,
        price_max=price_max,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )
    return get_market_distribution(db, filters, bucket_count=bucket_count)


@router.get("/comparables", response_model=ComparableResponse)
def get_market_comparables(
    brand: str = Query(...),
    model: str = Query(...),
    trim: str | None = Query(default=None),
    department: str | None = Query(default=None),
    municipality: str | None = Query(default=None),
    locality: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=1950, le=2100),
    mileage_km: Decimal | None = Query(default=None, ge=0),
    target_price_cop: Decimal | None = Query(default=None, ge=0),
    hybrid_flag: bool | None = Query(default=None),
    mhev_flag: bool | None = Query(default=None),
    outlier_flag: bool | None = Query(default=False),
    is_active: bool | None = Query(default=True),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> ComparableResponse:
    filters = _build_filters(
        brand=brand,
        model=model,
        trim=trim,
        department=department,
        municipality=municipality,
        locality=locality,
        fuel_type=fuel_type,
        transmission=transmission,
        hybrid_flag=hybrid_flag,
        mhev_flag=mhev_flag,
        outlier_flag=outlier_flag,
        is_active=is_active,
    )
    return get_comparables(
        db,
        filters,
        target_year=year,
        target_mileage_km=mileage_km,
        target_price_cop=target_price_cop,
        limit=limit,
    )
