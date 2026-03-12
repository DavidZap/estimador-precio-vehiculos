from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MarketSearchFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    brand: str | None = None
    model: str | None = None
    trim: str | None = None
    department: str | None = None
    municipality: str | None = None
    locality: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    year_min: int | None = Field(default=None, ge=1950, le=2100)
    year_max: int | None = Field(default=None, ge=1950, le=2100)
    mileage_min: Decimal | None = Field(default=None, ge=0)
    mileage_max: Decimal | None = Field(default=None, ge=0)
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    hybrid_flag: bool | None = None
    mhev_flag: bool | None = None
    outlier_flag: bool | None = None
    is_active: bool | None = True


class MarketListingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_name: str
    source_listing_id: str
    source_url: str | None = None
    image_url: str | None = None
    title_clean: str | None = None
    price_cop: Decimal | None = None
    year: int | None = None
    mileage_km: Decimal | None = None
    brand_std: str | None = None
    model_std: str | None = None
    trim_std: str | None = None
    version_std: str | None = None
    engine_displacement_std: str | None = None
    transmission_std: str | None = None
    fuel_type_std: str | None = None
    department_std: str | None = None
    municipality_std: str | None = None
    locality_std: str | None = None
    city_std: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    outlier_flag: bool
    is_active: bool
    updated_at: datetime


class MarketListingsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MarketListingItem]


class FilterOption(BaseModel):
    value: str | int | bool
    count: int


class MarketFiltersResponse(BaseModel):
    brands: list[FilterOption]
    models: list[FilterOption]
    trims: list[FilterOption]
    departments: list[FilterOption]
    municipalities: list[FilterOption]
    localities: list[FilterOption]
    fuel_types: list[FilterOption]
    transmissions: list[FilterOption]
    years: list[FilterOption]


class MarketSummaryResponse(BaseModel):
    total_listings: int
    active_listings: int
    outlier_listings: int
    avg_price_cop: Decimal | None = None
    median_price_cop: Decimal | None = None
    min_price_cop: Decimal | None = None
    max_price_cop: Decimal | None = None
    avg_mileage_km: Decimal | None = None
    min_year: int | None = None
    max_year: int | None = None


class PriceDistributionBucket(BaseModel):
    start_price_cop: Decimal
    end_price_cop: Decimal
    count: int


class MarketDistributionResponse(BaseModel):
    total_listings: int
    bucket_count: int
    min_price_cop: Decimal | None = None
    max_price_cop: Decimal | None = None
    p10_price_cop: Decimal | None = None
    p25_price_cop: Decimal | None = None
    p50_price_cop: Decimal | None = None
    p75_price_cop: Decimal | None = None
    p90_price_cop: Decimal | None = None
    buckets: list[PriceDistributionBucket]


class ComparableSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    brand: str
    model: str
    trim: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    mileage_km: Decimal | None = Field(default=None, ge=0)
    target_price_cop: Decimal | None = Field(default=None, ge=0)
    transmission: str | None = None
    fuel_type: str | None = None
    department: str | None = None
    municipality: str | None = None
    hybrid_flag: bool | None = None
    mhev_flag: bool | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ComparableItem(MarketListingItem):
    comparable_score: Decimal


class ComparableResponse(BaseModel):
    total_candidates: int
    items: list[ComparableItem]
