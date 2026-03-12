from __future__ import annotations

from typing import Any

import httpx

from vehicle_price_estimator.config.logging import get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.parser import slugify_query


LOGGER = get_logger(__name__)


class MercadoLibreClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.timeout = httpx.Timeout(self.settings.mercadolibre_timeout_seconds)

    @staticmethod
    def _default_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        }

    def search_items_api(self, query: str, limit: int, offset: int = 0) -> tuple[int, dict[str, Any]]:
        url = f"{self.settings.mercadolibre_api_base_url}/sites/{self.settings.mercadolibre_site_id}/search"
        params = {
            "q": query,
            "limit": limit,
            "offset": offset,
        }

        try:
            with httpx.Client(timeout=self.timeout, headers=self._default_headers()) as client:
                response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            LOGGER.warning("Mercado Libre API search request failed: %s", exc)
            return 0, {"error": str(exc)}

        payload: dict[str, Any]
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw_text": response.text}

        LOGGER.info("Mercado Libre API search returned status %s.", response.status_code)
        return response.status_code, payload

    def get_item_detail_api(self, item_id: str) -> tuple[int, dict[str, Any]]:
        url = f"{self.settings.mercadolibre_api_base_url}/items/{item_id}"

        try:
            with httpx.Client(timeout=self.timeout, headers=self._default_headers()) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            LOGGER.warning("Mercado Libre item detail request failed for %s: %s", item_id, exc)
            return 0, {"error": str(exc), "id": item_id}

        payload: dict[str, Any]
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw_text": response.text}

        LOGGER.info("Mercado Libre item detail for %s returned status %s.", item_id, response.status_code)
        return response.status_code, payload

    def search_items_web(self, query: str) -> tuple[int, str]:
        slug = slugify_query(query)
        url = f"{self.settings.mercadolibre_web_base_url}/{slug}"

        try:
            with httpx.Client(
                timeout=self.timeout,
                headers=self._default_headers(),
                follow_redirects=True,
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            LOGGER.warning("Mercado Libre web search request failed: %s", exc)
            return 0, str(exc)

        LOGGER.info("Mercado Libre web search returned status %s.", response.status_code)
        return response.status_code, response.text

    def search_items_browser(self, query: str) -> tuple[int, str]:
        slug = slugify_query(query)
        url = f"{self.settings.mercadolibre_web_base_url}/{slug}"

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            LOGGER.warning("Playwright is not installed. Browser fallback is unavailable.")
            return 0, "playwright_not_installed"

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.settings.mercadolibre_browser_headless)
                context = browser.new_context(
                    locale="es-CO",
                    user_agent=self._default_headers()["User-Agent"],
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.settings.mercadolibre_timeout_seconds * 1000)
                page.wait_for_timeout(self.settings.mercadolibre_browser_wait_ms)
                html = page.content()
                browser.close()
        except Exception as exc:
            LOGGER.warning("Mercado Libre browser fallback failed: %s", exc)
            return 0, str(exc)

        LOGGER.info("Mercado Libre browser search completed.")
        return 200, html
