from datetime import datetime, timezone
from pathlib import Path

from vehicle_price_estimator.config.logging import configure_logging, get_logger
from vehicle_price_estimator.config.settings import get_settings
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.connector import MercadoLibreConnector
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.models import SearchBatch
from vehicle_price_estimator.infrastructure.connectors.mercadolibre.parser import build_payload_hash
from vehicle_price_estimator.infrastructure.db.models.raw_listing_payload import ListingPayloadModel
from vehicle_price_estimator.infrastructure.db.models.raw_run import ExtractRunModel
from vehicle_price_estimator.infrastructure.db.session import SessionLocal
from vehicle_price_estimator.infrastructure.storage.local_storage import LocalFileStorage


LOGGER = get_logger(__name__)


def _persist_batch_artifacts(
    storage: LocalFileStorage,
    extract_run_id: str,
    batch: SearchBatch,
) -> tuple[str | None, str | None]:
    batch_json_path: str | None = None
    batch_html_path: str | None = None

    if batch.raw_payload is not None:
        batch_json_relative = f"{extract_run_id}/search/search_response.json"
        batch_json_path = str(storage.write_json(batch_json_relative, batch.raw_payload))

    if batch.raw_html is not None:
        batch_html_relative = f"{extract_run_id}/search/search_response.html"
        batch_html_path = str(storage.write_text(batch_html_relative, batch.raw_html))

    return batch_json_path, batch_html_path


def _persist_listing_artifacts(
    storage: LocalFileStorage,
    extract_run_id: str,
    source_listing_id: str,
    payload: dict,
) -> str:
    relative_path = f"{extract_run_id}/items/{source_listing_id}.json"
    return str(storage.write_json(relative_path, payload))


def run_extraction_pipeline(
    query: str = "vehiculos usados colombia",
    limit: int | None = None,
    fetch_item_details: bool = True,
) -> str:
    settings = get_settings()
    configure_logging(settings.log_level)
    connector = MercadoLibreConnector()
    storage = LocalFileStorage(Path(settings.raw_storage_path))
    query_limit = limit or settings.mercadolibre_default_limit

    with SessionLocal() as db:
        extract_run = ExtractRunModel(
            connector_type="mercadolibre_connector_v0_2",
            status="running",
            query_params={
                "query": query,
                "limit": query_limit,
                "fetch_item_details": fetch_item_details,
            },
            started_at=datetime.now(timezone.utc),
        )
        db.add(extract_run)
        db.commit()
        db.refresh(extract_run)

        batch = connector.fetch_listings(
            query=query,
            limit=query_limit,
            fetch_item_details=fetch_item_details,
        )
        payloads = batch.payloads
        batch_json_path, batch_html_path = _persist_batch_artifacts(storage, str(extract_run.id), batch)

        for payload in payloads:
            item_json_path = _persist_listing_artifacts(
                storage=storage,
                extract_run_id=str(extract_run.id),
                source_listing_id=payload.source_listing_id,
                payload=payload.payload,
            )
            db.add(
                ListingPayloadModel(
                    extract_run_id=extract_run.id,
                    source_listing_id=payload.source_listing_id,
                    source_url=payload.source_url,
                    payload_json=payload.payload,
                    payload_html_path=payload.payload_html_path,
                    payload_json_path=item_json_path,
                    payload_hash=build_payload_hash(payload.payload),
                    observed_at=payload.observed_at,
                    http_status=payload.http_status,
                    parser_version=payload.parser_version,
                )
            )

        extract_run.items_discovered = len(payloads)
        extract_run.items_persisted = len(payloads)
        extract_run.status = "completed"
        extract_run.finished_at = datetime.now(timezone.utc)
        extract_run.notes = (
            f"strategy={batch.strategy}; "
            f"search_json={batch_json_path}; "
            f"search_html={batch_html_path}; "
            f"error={batch.error_message}"
        )
        db.commit()

    LOGGER.info(
        "Extraction pipeline finished with %s payloads using strategy '%s'.",
        len(payloads),
        batch.strategy,
    )
    return str(extract_run.id)
