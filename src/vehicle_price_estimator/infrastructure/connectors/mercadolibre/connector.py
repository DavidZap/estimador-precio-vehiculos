from __future__ import annotations

from vehicle_price_estimator.config.logging import get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.client import MercadoLibreClient
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.models import ListingPayload, SearchBatch
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.parser import (
    extract_item_ids_from_html,
    extract_permalink_map_from_html,
    normalize_search_results,
)


LOGGER = get_logger(__name__)


class MercadoLibreConnector:
    def __init__(self, client: MercadoLibreClient | None = None) -> None:
        self.client = client or MercadoLibreClient()
        self.settings = get_settings()

    def fetch_listings(self, query: str, limit: int = 20, fetch_item_details: bool = True) -> SearchBatch:
        status_code, search_payload = self.client.search_items_api(query=query, limit=limit)

        if status_code == 200 and isinstance(search_payload, dict):
            search_results = normalize_search_results(search_payload.get("results", []))
            payloads = self._build_payloads_from_api_results(
                search_results,
                fetch_item_details=fetch_item_details,
            )
            return SearchBatch(
                strategy="api_search",
                query=query,
                payloads=payloads,
                raw_payload=search_payload,
                status_code=status_code,
            )

        LOGGER.warning("API search unavailable for query '%s'. Falling back to web strategy.", query)
        web_status_code, html = self.client.search_items_web(query=query)
        payloads = self._build_payloads_from_html(html, fetch_item_details=fetch_item_details)

        strategy = "web_search"
        if not payloads and self.settings.mercadolibre_enable_browser_fallback:
            LOGGER.warning(
                "Simple web fallback returned no items for '%s'. Trying browser fallback.",
                query,
            )
            browser_status_code, browser_html = self.client.search_items_browser(query=query)
            browser_payloads = self._build_payloads_from_html(
                browser_html,
                fetch_item_details=fetch_item_details,
            )
            if browser_payloads:
                payloads = browser_payloads
                html = browser_html
                web_status_code = browser_status_code
                strategy = "browser_search"

        return SearchBatch(
            strategy=strategy,
            query=query,
            payloads=payloads,
            raw_html=html,
            status_code=web_status_code,
            error_message=(
                None if status_code == 200 else f"API search returned status {status_code}"
            ),
        )

    def _build_payloads_from_api_results(
        self,
        results: list[dict],
        fetch_item_details: bool,
    ) -> list[ListingPayload]:
        payloads: list[ListingPayload] = []

        for result in results:
            item_id = str(result["id"])
            item_payload = result
            item_status = 200

            if fetch_item_details:
                detail_status, detail_payload = self.client.get_item_detail_api(item_id)
                if detail_status == 200 and isinstance(detail_payload, dict):
                    item_payload = detail_payload
                    item_status = detail_status

            payloads.append(
                ListingPayload(
                    source_listing_id=item_id,
                    source_url=result.get("permalink") or item_payload.get("permalink", ""),
                    payload=item_payload,
                    http_status=item_status,
                    parser_version="0.2",
                    extraction_strategy="api_search",
                )
            )

        return payloads

    def _build_payloads_from_html(self, html: str, fetch_item_details: bool) -> list[ListingPayload]:
        item_ids = extract_item_ids_from_html(html)
        permalink_map = extract_permalink_map_from_html(html)
        payloads: list[ListingPayload] = []

        for item_id in item_ids:
            payload: dict = {"id": item_id, "source": "html_search_fallback"}
            item_status = 200

            if fetch_item_details:
                detail_status, detail_payload = self.client.get_item_detail_api(item_id)
                if detail_status == 200 and isinstance(detail_payload, dict):
                    payload = detail_payload
                    item_status = detail_status
                else:
                    item_status = detail_status

            payloads.append(
                ListingPayload(
                    source_listing_id=item_id,
                    source_url=payload.get("permalink") or permalink_map.get(item_id, ""),
                    payload=payload,
                    http_status=item_status,
                    parser_version="0.2",
                    extraction_strategy="web_search",
                )
            )

        return payloads
