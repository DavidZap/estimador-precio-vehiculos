import json
import re
from hashlib import sha256
from typing import Any


def build_payload_hash(payload: dict) -> str:
    canonical_payload = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return sha256(canonical_payload.encode("utf-8")).hexdigest()


def slugify_query(query: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", query.strip().lower())
    return normalized.strip("-") or "vehiculos"


def extract_item_ids_from_html(html: str) -> list[str]:
    matches = re.findall(r'"id":"(MCO\d+)"', html)
    if matches:
        return list(dict.fromkeys(matches))

    matches = re.findall(r"\b(MCO\d{6,})\b", html)
    return list(dict.fromkeys(matches))


def extract_permalink_map_from_html(html: str) -> dict[str, str]:
    item_ids = extract_item_ids_from_html(html)
    permalink_map: dict[str, str] = {}

    for item_id in item_ids:
        permalink_map[item_id] = ""

    for item_id, url in re.findall(r'"id":"(MCO\d+)".{0,500}?"permalink":"(https:[^"]+)"', html):
        permalink_map[item_id] = url.replace("\\/", "/")

    return permalink_map


def normalize_search_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for result in results:
        if not result.get("id"):
            continue
        normalized.append(result)

    return normalized
