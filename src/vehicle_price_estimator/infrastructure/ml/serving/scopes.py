from __future__ import annotations


MAINSTREAM_BRANDS = ("Toyota", "Mazda", "Renault", "Chevrolet", "Volkswagen")


def normalize_brand_list(brands: list[str] | None) -> list[str]:
    if not brands:
        return []
    return sorted({brand.strip() for brand in brands if brand and brand.strip()})


def infer_model_scope(include_brands: list[str] | None) -> str:
    normalized = normalize_brand_list(include_brands)
    if not normalized:
        return "global"
    if normalized == sorted(MAINSTREAM_BRANDS):
        return "mainstream"
    return "custom"


def resolve_requested_scope(brand: str) -> str:
    return "mainstream" if brand.strip() in MAINSTREAM_BRANDS else "global"


def resolve_registry_scope(model_scope: str | None, scope_filters_json: dict | None, feature_schema_json: dict | None) -> str:
    scope_filters = scope_filters_json or feature_schema_json or {}
    inferred_scope = infer_model_scope(scope_filters.get("include_brands"))
    if model_scope == "global" and inferred_scope != "global":
        return inferred_scope
    return model_scope or inferred_scope or "global"
