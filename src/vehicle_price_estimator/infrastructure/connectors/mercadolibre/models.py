from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ListingPayload:
    source_listing_id: str
    source_url: str
    payload: dict[str, Any]
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    http_status: int = 200
    parser_version: str = "0.1"
    extraction_strategy: str = "api_search"
    payload_json_path: str | None = None
    payload_html_path: str | None = None


@dataclass(slots=True)
class SearchBatch:
    strategy: str
    query: str
    payloads: list[ListingPayload]
    raw_payload: dict[str, Any] | None = None
    raw_html: str | None = None
    status_code: int | None = None
    error_message: str | None = None
