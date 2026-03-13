from __future__ import annotations

import os
from decimal import Decimal

import httpx
import pandas as pd
import pydeck as pdk
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://localhost:8000/api/v1")
MAINSTREAM_BRANDS = {"Toyota", "Mazda", "Renault", "Chevrolet", "Volkswagen"}
KNOWN_BRANDS = {
    "Acura",
    "Alfa Romeo",
    "Audi",
    "BMW",
    "BYD",
    "Chevrolet",
    "Chery",
    "Citroen",
    "Cupra",
    "DFSK",
    "Dodge",
    "DS",
    "Fiat",
    "Ford",
    "Foton",
    "Great Wall",
    "Honda",
    "Hyundai",
    "Isuzu",
    "JAC",
    "Jaguar",
    "Jeep",
    "Kia",
    "Land Rover",
    "Lexus",
    "Mazda",
    "Mercedes-Benz",
    "MG",
    "Mini",
    "Mitsubishi",
    "Nissan",
    "Opel",
    "Peugeot",
    "Porsche",
    "RAM",
    "Renault",
    "Seat",
    "Skoda",
    "SsangYong",
    "Subaru",
    "Suzuki",
    "Toyota",
    "Volkswagen",
    "Volvo",
}
BANNED_OPTION_TOKENS = {
    "camiseta",
    "camisa",
    "chaqueta",
    "blusa",
    "jean",
    "jeans",
    "sudadera",
    "gorra",
    "tenis",
    "zapato",
    "zapatilla",
    "pantalon",
    "bolso",
    "reloj",
    "perfume",
    "celular",
    "iphone",
    "samsung",
}
CITY_COORDINATE_FALLBACKS = {
    ("Bogota D.C.", "Bogota D.C."): (4.7110, -74.0721),
    ("Antioquia", "Medellin"): (6.2442, -75.5812),
    ("Valle Del Cauca", "Cali"): (3.4516, -76.5320),
    ("Atlantico", "Barranquilla"): (10.9878, -74.7889),
    ("Santander", "Bucaramanga"): (7.1193, -73.1227),
    ("Risaralda", "Pereira"): (4.8143, -75.6946),
    ("Meta", "Villavicencio"): (4.1420, -73.6266),
    ("Bolivar", "Cartagena De Indias"): (10.3910, -75.4794),
}


def _clean_params(params: dict | None) -> dict | None:
    if params is None:
        return None
    cleaned: dict = {}
    for key, value in params.items():
        if value in (None, ""):
            continue
        cleaned[key] = value
    return cleaned


def _json_ready(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _api_get(base_url: str, path: str, params: dict | None = None) -> dict:
    response = httpx.get(f"{base_url}{path}", params=_clean_params(params), timeout=30.0)
    response.raise_for_status()
    return response.json()


def _api_post(base_url: str, path: str, payload: dict) -> dict:
    response = httpx.post(f"{base_url}{path}", json=_json_ready(payload), timeout=60.0)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=300, show_spinner=False)
def load_filters(base_url: str, params: dict | None = None) -> dict:
    return _api_get(base_url, "/market/filters", params=params)


@st.cache_data(ttl=180, show_spinner=False)
def load_summary(base_url: str, params: dict) -> dict:
    return _api_get(base_url, "/market/summary", params=params)


@st.cache_data(ttl=180, show_spinner=False)
def load_distribution(base_url: str, params: dict) -> dict:
    return _api_get(base_url, "/market/distribution", params=params)


@st.cache_data(ttl=120, show_spinner=False)
def load_listings(base_url: str, params: dict) -> dict:
    return _api_get(base_url, "/market/listings", params=params)


@st.cache_data(ttl=120, show_spinner=False)
def load_active_models(base_url: str) -> dict:
    return _api_get(base_url, "/predictions/models/active")


def _format_cop(value: float | int | str | Decimal | None) -> str:
    if value in (None, ""):
        return "COP 0"
    return f"COP {float(value):,.0f}"


def _format_number(value: float | int | str | Decimal | None) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):,.0f}"


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_label(value) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _fallback_coordinates(department: str | None, municipality: str | None) -> tuple[float, float] | tuple[None, None]:
    clean_department = _safe_label(department)
    clean_municipality = _safe_label(municipality)
    if not clean_department or not clean_municipality:
        return None, None
    return CITY_COORDINATE_FALLBACKS.get((clean_department, clean_municipality), (None, None))


def _is_reasonable_option(value: str, *, field_name: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(token in lowered for token in BANNED_OPTION_TOKENS):
        return False
    if field_name == "brand":
        return normalized in KNOWN_BRANDS
    if field_name in {"department", "municipality", "locality"} and len(normalized) > 50:
        return False
    if field_name == "engine":
        try:
            numeric = float(normalized.replace(",", "."))
            return 0.6 <= numeric <= 8.0
        except ValueError:
            return False
    if field_name in {"model", "trim"} and len(normalized) > 35:
        return False
    if len(normalized) > 40:
        return False
    if not any(char.isalpha() for char in normalized):
        return normalized in {"1", "2", "3", "Q3", "Q5", "X1", "X3", "X5"}
    return True


def _facet_values(payload: dict, key: str, *, field_name: str | None = None) -> list[str]:
    values: list[str] = []
    for item in payload.get(key, []):
        value = item.get("value")
        if value in (None, ""):
            continue
        candidate = str(value).strip()
        if field_name and not _is_reasonable_option(candidate, field_name=field_name):
            continue
        values.append(candidate)
    return values


def _select_option(
    label: str,
    options: list[str],
    *,
    key: str,
    default: str | None = None,
    allow_blank: bool = True,
    sidebar: bool = False,
    container=None,
) -> str:
    normalized_options = sorted({option for option in options if option})
    if allow_blank:
        normalized_options = [""] + normalized_options

    fallback = ""
    if not allow_blank and normalized_options:
        fallback = normalized_options[0]
    if default and default in normalized_options:
        fallback = default

    current = st.session_state.get(key, fallback)
    if current not in normalized_options:
        current = fallback
        st.session_state[key] = current

    target = container if container is not None else (st.sidebar if sidebar else st)
    index = normalized_options.index(current) if current in normalized_options else 0
    return target.selectbox(label, normalized_options, index=index, key=key)


def _render_highlight_card(title: str, value: str, subtitle: str = "", *, tone: str = "default") -> None:
    tone_class = {
        "primary": "result-card-primary",
        "success": "result-card-success",
        "warning": "result-card-warning",
    }.get(tone, "result-card-default")
    st.markdown(
        f"""
        <div class="result-card {tone_class}">
            <div class="result-card-title">{title}</div>
            <div class="result-card-value">{value}</div>
            <div class="result-card-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_comparable_cards(comparables: list[dict]) -> None:
    for offset in range(0, len(comparables), 3):
        row = st.columns(3)
        for column, comparable in zip(row, comparables[offset : offset + 3], strict=False):
            with column:
                title = comparable.get("title_clean") or f"{comparable.get('brand_std', '')} {comparable.get('model_std', '')}".strip()
                location = " / ".join(
                    [
                        item
                        for item in [
                            comparable.get("municipality_std"),
                            comparable.get("locality_std"),
                        ]
                        if item
                    ]
                )
                st.markdown(
                    f"""
                    <div class="comparable-card">
                        <div class="comparable-title">{title}</div>
                        <div class="comparable-price">{_format_cop(comparable.get("price_cop"))}</div>
                        <div class="comparable-meta">Ano {comparable.get("year", "-")} · {_format_number(comparable.get("mileage_km"))} km</div>
                        <div class="comparable-meta">{location or 'Ubicacion no disponible'}</div>
                        <div class="comparable-meta">Score comparable: {float(comparable.get("comparable_score") or 0):.2f}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if comparable.get("source_url"):
                    st.link_button("Ver anuncio", comparable["source_url"], use_container_width=True)


def _build_map_dataframe(items: list[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for item in items:
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        try:
            if latitude in (None, "") or longitude in (None, ""):
                latitude, longitude = _fallback_coordinates(item.get("department_std"), item.get("municipality_std"))
            if latitude in (None, "") or longitude in (None, ""):
                continue
            rows.append(
                {
                    "lat": float(latitude),
                    "lon": float(longitude),
                    "price_cop": float(item.get("price_cop") or 0),
                    "brand_std": item.get("brand_std"),
                    "model_std": item.get("model_std"),
                    "department_std": item.get("department_std"),
                    "municipality_std": item.get("municipality_std"),
                    "locality_std": item.get("locality_std"),
                }
            )
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.DataFrame()

    map_df = pd.DataFrame(rows)
    aggregated = (
        map_df.groupby(["lat", "lon", "municipality_std", "locality_std"], dropna=False)
        .agg(
            listing_count=("price_cop", "count"),
            median_price_cop=("price_cop", "median"),
        )
        .reset_index()
    )
    max_count = max(int(aggregated["listing_count"].max() or 1), 1)
    aggregated["radius"] = aggregated["listing_count"].apply(lambda value: 9000 + (value / max_count) * 24000)
    aggregated["tooltip_price"] = aggregated["median_price_cop"].map(_format_cop)
    max_price = max(float(aggregated["median_price_cop"].max() or 1), 1.0)
    aggregated["fill_color"] = aggregated["median_price_cop"].apply(
        lambda value: [
            min(240, int(120 + (float(value) / max_price) * 90)),
            max(70, int(165 - (float(value) / max_price) * 65)),
            45,
            180,
        ]
    )
    aggregated["tooltip_zone"] = aggregated.apply(
        lambda row: " / ".join(
            [
                item
                for item in [
                    _safe_label(row["municipality_std"]),
                    _safe_label(row["locality_std"]),
                ]
                if item and item != "-"
            ]
        )
        or "Zona sin detalle",
        axis=1,
    )
    return aggregated


def _apply_zone_filter(dataframe: pd.DataFrame, zone_filter: dict | None) -> pd.DataFrame:
    if dataframe.empty or not zone_filter:
        return dataframe
    filtered = dataframe.copy()
    municipality = zone_filter.get("municipality")
    locality = zone_filter.get("locality")
    if municipality:
        filtered = filtered[filtered["municipality_std"].fillna("-") == municipality]
    if locality and locality != "-":
        filtered = filtered[filtered["locality_std"].fillna("-") == locality]
    return filtered


@st.cache_data(ttl=120, show_spinner=False)
def load_estimator_catalog(
    base_url: str,
    brand: str | None,
    model: str | None,
    department: str | None,
    municipality: str | None,
) -> dict:
    filters_payload = load_filters(
        base_url,
        {
            "brand": brand or None,
            "model": model or None,
            "department": department or None,
            "municipality": municipality or None,
            "is_active": True,
            "outlier_flag": False,
        },
    )
    listings_payload = load_listings(
        base_url,
        {
            "brand": brand or None,
            "model": model or None,
            "department": department or None,
            "municipality": municipality or None,
            "is_active": True,
            "outlier_flag": False,
            "page": 1,
            "page_size": 100,
        },
    )
    items = listings_payload.get("items", [])
    trims = sorted(
        {
            str(item["trim_std"]).strip()
            for item in items
            if item.get("trim_std") and _is_reasonable_option(str(item["trim_std"]), field_name="trim")
        }
    )
    engines = sorted(
        {
            str(item["engine_displacement_std"]).strip()
            for item in items
            if item.get("engine_displacement_std")
            and _is_reasonable_option(str(item["engine_displacement_std"]), field_name="engine")
        }
    )
    vehicle_types = sorted(
        {
            str(item["vehicle_type_std"]).strip()
            for item in items
            if item.get("vehicle_type_std") and _is_reasonable_option(str(item["vehicle_type_std"]), field_name="vehicle_type")
        }
    )
    return {
        "filters": filters_payload,
        "trims": trims,
        "engines": engines,
        "vehicle_types": vehicle_types,
    }


def _build_market_filters(filters_payload: dict) -> tuple[dict, dict]:
    active_filters: dict[str, str | int | bool | None] = {}

    base_scope = {"is_active": True, "outlier_flag": False}
    brands = _facet_values(filters_payload, "brands", field_name="brand")
    filter_box = st.container(border=True)
    filter_box.caption("Refina el inventario por segmento, tiempo y ubicacion.")

    row1 = filter_box.columns(4)
    selected_brand = _select_option("Marca", brands, key="market_brand", allow_blank=True, container=row1[0])
    if selected_brand:
        active_filters["brand"] = selected_brand

    model_scope = load_filters(base_url=st.session_state["api_base_url"], params={**base_scope, **active_filters})
    models = _facet_values(model_scope, "models", field_name="model")
    selected_model = _select_option("Modelo", models, key="market_model", allow_blank=True, container=row1[1])
    if selected_model:
        active_filters["model"] = selected_model

    geography_scope = load_filters(base_url=st.session_state["api_base_url"], params={**base_scope, **active_filters})
    years = [item["value"] for item in geography_scope.get("years", []) if isinstance(item.get("value"), int)]
    min_year = int(min(years)) if years else 2010
    max_year = int(max(years)) if years else 2026
    selected_year_range = row1[2].slider("Rango de ano", min_year, max_year, (min_year, max_year))
    active_filters["year_min"] = selected_year_range[0]
    active_filters["year_max"] = selected_year_range[1]

    departments = _facet_values(geography_scope, "departments", field_name="department")
    selected_department = _select_option(
        "Departamento",
        departments,
        key="market_department",
        allow_blank=True,
        container=row1[3],
    )
    if selected_department:
        active_filters["department"] = selected_department

    municipality_scope = load_filters(base_url=st.session_state["api_base_url"], params={**base_scope, **active_filters})
    municipalities = _facet_values(municipality_scope, "municipalities", field_name="municipality")
    row2 = filter_box.columns(4)
    selected_municipality = _select_option(
        "Municipio",
        municipalities,
        key="market_municipality",
        allow_blank=True,
        container=row2[0],
    )
    if selected_municipality:
        active_filters["municipality"] = selected_municipality

    local_scope = load_filters(base_url=st.session_state["api_base_url"], params={**base_scope, **active_filters})
    localities = _facet_values(local_scope, "localities", field_name="locality")
    selected_locality = _select_option(
        "Localidad",
        localities,
        key="market_locality",
        allow_blank=True,
        container=row2[1],
    )
    if selected_locality:
        active_filters["locality"] = selected_locality

    final_scope = load_filters(base_url=st.session_state["api_base_url"], params={**base_scope, **active_filters})
    transmissions = _facet_values(final_scope, "transmissions", field_name="transmission")
    selected_transmission = _select_option(
        "Transmision",
        transmissions,
        key="market_transmission",
        allow_blank=True,
        container=row2[2],
    )
    if selected_transmission:
        active_filters["transmission"] = selected_transmission

    fuel_types = _facet_values(final_scope, "fuel_types", field_name="fuel_type")
    selected_fuel = _select_option(
        "Combustible",
        fuel_types,
        key="market_fuel_type",
        allow_blank=True,
        container=row2[3],
    )
    if selected_fuel:
        active_filters["fuel_type"] = selected_fuel

    include_outliers = filter_box.toggle("Incluir outliers", value=False)
    active_filters["outlier_flag"] = None if include_outliers else False
    active_filters["is_active"] = True

    display_filters = {
        "Marca": selected_brand or "Todas",
        "Modelo": selected_model or "Todos",
        "Ano": f"{selected_year_range[0]} - {selected_year_range[1]}",
        "Departamento": selected_department or "Todos",
        "Municipio": selected_municipality or "Todos",
        "Localidad": selected_locality or "Todas",
        "Transmision": selected_transmission or "Todas",
        "Combustible": selected_fuel or "Todos",
    }
    return active_filters, display_filters


def render_market_explorer(base_url: str) -> None:
    st.session_state["api_base_url"] = base_url
    filters_payload = load_filters(base_url)
    st.subheader("Explorador de mercado")
    st.caption("Explora la oferta capturada, compara segmentos y revisa la distribucion observable del mercado.")
    query_filters, display_filters = _build_market_filters(filters_payload)

    cols = st.columns(4)
    for index, (label, value) in enumerate(display_filters.items()):
        cols[index % 4].metric(label, value)

    summary = load_summary(base_url, query_filters)
    summary_cols = st.columns(5)
    summary_cols[0].metric("Inventario", summary.get("total_listings", 0))
    summary_cols[1].metric("Activos", summary.get("active_listings", 0))
    summary_cols[2].metric("Precio mediano", _format_cop(summary.get("median_price_cop")))
    summary_cols[3].metric("Precio promedio", _format_cop(summary.get("avg_price_cop")))
    summary_cols[4].metric("Km promedio", f"{float(summary.get('avg_mileage_km') or 0):,.0f}")

    distribution = load_distribution(base_url, {**query_filters, "bucket_count": 8})
    listings = load_listings(base_url, {**query_filters, "page": 1, "page_size": 25})
    listing_items = listings.get("items", [])
    if not listing_items:
        st.info("No hay anuncios para los filtros seleccionados.")
        return

    listing_df = pd.DataFrame(listing_items)
    map_df = _build_map_dataframe(listing_items)
    geo_summary_rows = [
        {
            "municipio": item.get("municipality_std") or "-",
            "localidad": item.get("locality_std") or "-",
            "precio_cop": float(item.get("price_cop") or 0),
        }
        for item in listing_items
        if item.get("price_cop") not in (None, "")
    ]
    geo_summary_df = pd.DataFrame(geo_summary_rows) if geo_summary_rows else pd.DataFrame()
    if not geo_summary_df.empty:
        geo_summary_df = (
            geo_summary_df.groupby(["municipio", "localidad"], dropna=False)["precio_cop"]
            .median()
            .reset_index()
            .sort_values("precio_cop", ascending=False)
        )
        geo_summary_df["Precio medio"] = geo_summary_df["precio_cop"].map(_format_cop)
        geo_summary_df = geo_summary_df.rename(columns={"municipio": "Municipio", "localidad": "Localidad"})

    selected_zone = st.session_state.get("market_zone_filter")
    inventory_source_df = listing_df.copy()

    overview_tab, geo_tab, inventory_tab = st.tabs(["Panorama", "Geografia", "Inventario"])

    with overview_tab:
        overview_cols = st.columns([1.2, 1])
        with overview_cols[0]:
            if distribution.get("buckets"):
                chart_df = pd.DataFrame(
                    [
                        {
                            "bucket": f"{int(float(bucket['start_price_cop'])):,} - {int(float(bucket['end_price_cop'])):,}",
                            "count": bucket["count"],
                        }
                        for bucket in distribution["buckets"]
                    ]
                )
                with st.container(border=True):
                    st.caption("Distribucion de precios del segmento filtrado")
                    st.bar_chart(chart_df, x="bucket", y="count", horizontal=True)
        with overview_cols[1]:
            with st.container(border=True):
                st.caption("Precio vs kilometraje del segmento visible")
                scatter_candidates = listing_df.copy()
                if {"mileage_km", "price_cop"}.issubset(scatter_candidates.columns):
                    scatter_candidates["mileage_km"] = pd.to_numeric(scatter_candidates["mileage_km"], errors="coerce")
                    scatter_candidates["price_cop"] = pd.to_numeric(scatter_candidates["price_cop"], errors="coerce")
                    scatter_candidates = scatter_candidates.dropna(subset=["mileage_km", "price_cop"])
                    if not scatter_candidates.empty:
                        st.scatter_chart(scatter_candidates, x="mileage_km", y="price_cop", color="brand_std")
                    else:
                        st.info("No hay suficiente informacion numerica para este grafico.")
                else:
                    st.info("No hay suficiente informacion numerica para este grafico.")

        ranking_cols = st.columns(2)
        with ranking_cols[0]:
            with st.container(border=True):
                st.caption("Ranking visible de marcas")
                brand_rank_df = (
                    listing_df.groupby("brand_std", dropna=False)
                    .size()
                    .reset_index(name="anuncios")
                    .sort_values("anuncios", ascending=False)
                    .head(10)
                )
                if not brand_rank_df.empty:
                    st.bar_chart(brand_rank_df, x="brand_std", y="anuncios", horizontal=True)
                else:
                    st.info("No hay suficiente informacion para construir el ranking de marcas.")
        with ranking_cols[1]:
            with st.container(border=True):
                st.caption("Ranking visible de modelos")
                model_rank_df = listing_df.copy()
                model_rank_df["brand_model"] = (
                    model_rank_df["brand_std"].fillna("") + " " + model_rank_df["model_std"].fillna("")
                ).str.strip()
                model_rank_df = (
                    model_rank_df.groupby("brand_model", dropna=False)
                    .size()
                    .reset_index(name="anuncios")
                    .sort_values("anuncios", ascending=False)
                    .head(10)
                )
                if not model_rank_df.empty:
                    st.bar_chart(model_rank_df, x="brand_model", y="anuncios", horizontal=True)
                else:
                    st.info("No hay suficiente informacion para construir el ranking de modelos.")

    with geo_tab:
        geo_mode = st.radio(
            "Vista geografica",
            options=["Volumen de anuncios", "Precio mediano"],
            horizontal=True,
            key="geo_view_mode",
        )
        geo_cols = st.columns([1.4, 1])
        with geo_cols[0]:
            with st.container(border=True):
                st.caption("Mapa de anuncios capturados")
                if not map_df.empty:
                    view_state = pdk.ViewState(
                        latitude=float(map_df["lat"].mean()),
                        longitude=float(map_df["lon"].mean()),
                        zoom=5.8,
                        pitch=18,
                    )
                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=map_df,
                        get_position="[lon, lat]",
                        get_radius="radius" if geo_mode == "Volumen de anuncios" else 18000,
                        get_fill_color="fill_color" if geo_mode == "Precio mediano" else [174, 117, 46, 185],
                        get_line_color="[92, 63, 31, 220]",
                        line_width_min_pixels=1,
                        pickable=True,
                        stroked=True,
                        opacity=0.72,
                    )
                    tooltip = {
                        "html": "<b>{tooltip_zone}</b><br/>Anuncios: {listing_count}<br/>Precio mediano: {tooltip_price}",
                        "style": {
                            "backgroundColor": "#20150c",
                            "color": "white",
                            "borderRadius": "10px",
                        },
                    }
                    st.pydeck_chart(
                        pdk.Deck(
                            map_provider="carto",
                            map_style="light",
                            initial_view_state=view_state,
                            layers=[layer],
                            tooltip=tooltip,
                        ),
                        use_container_width=True,
                    )
                else:
                    st.info("Todavia no hay suficientes coordenadas limpias para dibujar el mapa de este filtro.")
        with geo_cols[1]:
            with st.container(border=True):
                st.caption("Precio mediano por zona visible")
                if selected_zone:
                    st.info(
                        f"Zona activa: {selected_zone.get('municipality', '-')}"
                        + (f" / {selected_zone.get('locality')}" if selected_zone.get("locality") not in (None, "", "-") else "")
                    )
                clear_zone = st.button("Limpiar zona", key="clear_market_zone", use_container_width=True)
                if clear_zone:
                    st.session_state["market_zone_filter"] = None
                    st.rerun()
                if not geo_summary_df.empty:
                    zone_event = st.dataframe(
                        geo_summary_df[["Municipio", "Localidad", "Precio medio"]],
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key="market_geo_zone_table",
                    )
                    selected_rows = zone_event.selection.rows if zone_event and zone_event.selection else []
                    if selected_rows:
                        selected_row = geo_summary_df.iloc[selected_rows[0]]
                        zone_payload = {
                            "municipality": selected_row["Municipio"],
                            "locality": selected_row["Localidad"],
                        }
                        if st.session_state.get("market_zone_filter") != zone_payload:
                            st.session_state["market_zone_filter"] = zone_payload
                            st.rerun()
                else:
                    st.info("No hay suficiente informacion geografica para resumir este segmento.")

    with inventory_tab:
        if selected_zone:
            inventory_source_df = _apply_zone_filter(inventory_source_df, selected_zone)
            st.caption(
                "Inventario filtrado por zona: "
                f"{selected_zone.get('municipality', '-')}"
                + (
                    f" / {selected_zone.get('locality')}"
                    if selected_zone.get("locality") not in (None, "", "-")
                    else ""
                )
            )
        with st.container(border=True):
            st.caption("Inventario capturado")
            listing_df = inventory_source_df.rename(
                columns={
                    "brand_std": "Marca",
                    "model_std": "Modelo",
                    "trim_std": "Trim",
                    "year": "Ano",
                    "mileage_km": "Kilometraje",
                    "price_cop": "Precio",
                    "department_std": "Departamento",
                    "municipality_std": "Municipio",
                    "locality_std": "Localidad",
                    "source_url": "Anuncio",
                }
            )
            if "Precio" in listing_df.columns:
                listing_df["Precio"] = listing_df["Precio"].map(_format_cop)
            if "Kilometraje" in listing_df.columns:
                listing_df["Kilometraje"] = listing_df["Kilometraje"].map(
                    lambda value: f"{float(value):,.0f} km" if value not in (None, "") else "-"
                )
            columns = ["Marca", "Modelo", "Trim", "Ano", "Kilometraje", "Precio", "Departamento", "Municipio", "Localidad", "Anuncio"]
            available_columns = [column for column in columns if column in listing_df.columns]
            st.dataframe(
                listing_df[available_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Anuncio": st.column_config.LinkColumn("Anuncio"),
                },
            )


def render_estimator(base_url: str) -> None:
    st.subheader("Estimador de precio")
    st.caption(
        "Las marcas mainstream usan el modelo mas fuerte del sistema. "
        "Las marcas no mainstream usan el modelo global y deben interpretarse con mayor cautela."
    )

    base_filters = load_filters(base_url, {"is_active": True, "outlier_flag": False})
    brands = _facet_values(base_filters, "brands", field_name="brand")
    departments = _facet_values(base_filters, "departments", field_name="department")

    vehicle_box = st.container(border=True)
    vehicle_box.markdown("#### Vehiculo")
    vehicle_box.caption("Primero define el vehiculo. Luego ajusta la ubicacion del mercado donde quieres estimar.")
    geo_box = st.container(border=True)
    geo_box.markdown("#### Ubicacion")
    geo_box.caption("La ubicacion ajusta la referencia de mercado, pero no redefine la configuracion mecanica del vehiculo.")

    vehicle_row1 = vehicle_box.columns(3)
    brand_std = _select_option(
        "Marca",
        brands,
        key="estimate_brand",
        default="Toyota",
        allow_blank=False,
        container=vehicle_row1[0],
    )

    model_filters = load_filters(
        base_url,
        {
            "brand": brand_std or None,
            "is_active": True,
            "outlier_flag": False,
        },
    )
    model_std = _select_option(
        "Modelo",
        _facet_values(model_filters, "models", field_name="model"),
        key="estimate_model",
        default="Corolla Cross",
        allow_blank=False,
        container=vehicle_row1[1],
    )

    product_catalog = load_estimator_catalog(
        base_url,
        brand=brand_std or None,
        model=model_std or None,
        department=None,
        municipality=None,
    )
    product_filters = product_catalog["filters"]
    trims = product_catalog["trims"]
    engines = product_catalog["engines"]
    vehicle_types = product_catalog["vehicle_types"]
    transmission_options = _facet_values(product_filters, "transmissions", field_name="transmission")
    fuel_options = _facet_values(product_filters, "fuel_types", field_name="fuel_type")
    trim_std = _select_option(
        "Version / trim",
        trims,
        key="estimate_trim",
        default="XEI",
        allow_blank=True,
        container=vehicle_row1[2],
    )

    vehicle_row2 = vehicle_box.columns(4)
    year = vehicle_row2[0].number_input("Ano", min_value=1950, max_value=2100, value=2022, step=1)
    mileage_km = vehicle_row2[1].number_input("Kilometraje", min_value=0, value=42000, step=1000)
    engine_displacement_std = _select_option(
        "Motor",
        engines,
        key="estimate_engine",
        default="2.0",
        allow_blank=True,
        container=vehicle_row2[2],
    )
    transmission_std = vehicle_row2[3].selectbox(
        "Transmision",
        [""] + transmission_options,
        index=0,
        key="estimate_transmission",
    )

    vehicle_row3 = vehicle_box.columns(4)
    fuel_type_std = vehicle_row3[0].selectbox("Combustible", [""] + fuel_options, index=0, key="estimate_fuel")
    vehicle_type_std = _select_option(
        "Tipo de vehiculo",
        vehicle_types,
        key="estimate_vehicle_type",
        default=None,
        allow_blank=True,
        container=vehicle_row3[1],
    )
    hybrid_flag = vehicle_row3[2].checkbox("Hibrido", value=fuel_type_std == "Hibrido")
    mhev_flag = vehicle_row3[3].checkbox("MHEV", value=False)

    geo_row1 = geo_box.columns(3)
    department_std = _select_option(
        "Departamento",
        departments,
        key="estimate_department",
        default="Bogota D.C.",
        allow_blank=False,
        container=geo_row1[0],
    )

    geography_filters = load_filters(
        base_url,
        {
            "department": department_std or None,
            "is_active": True,
            "outlier_flag": False,
        },
    )
    municipalities = _facet_values(geography_filters, "municipalities", field_name="municipality")
    municipality_std = _select_option(
        "Municipio",
        municipalities,
        key="estimate_municipality",
        default="Bogota D.C.",
        allow_blank=True,
        container=geo_row1[1],
    )

    locality_filters = load_filters(
        base_url,
        {
            "department": department_std or None,
            "municipality": municipality_std or None,
            "is_active": True,
            "outlier_flag": False,
        },
    )
    locality_options = _facet_values(locality_filters, "localities", field_name="locality")
    locality_std = _select_option(
        "Localidad",
        locality_options,
        key="estimate_locality",
        default="Suba",
        allow_blank=True,
        container=geo_row1[2],
    )
    submitted = st.button("Estimar precio", use_container_width=True, type="primary")

    if not submitted:
        return

    payload = {
        "brand_std": brand_std,
        "model_std": model_std,
        "trim_std": _clean_text(trim_std),
        "year": int(year),
        "mileage_km": Decimal(str(mileage_km)),
        "engine_displacement_std": _clean_text(engine_displacement_std),
        "transmission_std": _clean_text(transmission_std),
        "fuel_type_std": _clean_text(fuel_type_std),
        "department_std": _clean_text(department_std),
        "municipality_std": _clean_text(municipality_std),
        "locality_std": _clean_text(locality_std),
        "vehicle_type_std": _clean_text(vehicle_type_std),
        "hybrid_flag": hybrid_flag,
        "mhev_flag": mhev_flag,
    }

    try:
        prediction = _api_post(base_url, "/predictions/estimate", payload)
    except httpx.HTTPError as exc:
        st.error(f"No fue posible obtener la prediccion: {exc}")
        return

    st.markdown("#### Resultado estimado")
    result_cols = st.columns([1.4, 1, 1, 1])
    with result_cols[0]:
        _render_highlight_card(
            "Precio estimado",
            _format_cop(prediction["predicted_price_cop"]),
            "Referencia observable de mercado",
            tone="primary",
        )
    with result_cols[1]:
        _render_highlight_card(
            "Rango inferior",
            _format_cop(prediction["predicted_range_lower_cop"]),
            "Piso de referencia",
        )
    with result_cols[2]:
        _render_highlight_card(
            "Rango superior",
            _format_cop(prediction["predicted_range_upper_cop"]),
            "Techo de referencia",
        )
    with result_cols[3]:
        _render_highlight_card(
            "Confianza",
            prediction["confidence_label"].title(),
            f"Score {prediction['confidence_score']:.2f}",
            tone="success" if prediction["confidence_score"] >= 0.8 else "warning",
        )

    scope_used = prediction["model_scope_used"]
    is_mainstream = payload["brand_std"] in MAINSTREAM_BRANDS
    with st.container(border=True):
        detail_cols = st.columns(4)
        detail_cols[0].metric("Modelo usado", prediction["model_name"])
        detail_cols[1].metric("Scope usado", scope_used)
        detail_cols[2].metric("Comparables", prediction["comparables_count"])
        detail_cols[3].metric("Metodo de rango", prediction["range_method_used"])

    if not is_mainstream or scope_used == "global":
        st.warning(
            "Esta prediccion usa el modelo global o pertenece a un segmento no mainstream. "
            "Tomala como una referencia de mercado inicial y apoyate mas en comparables y contexto."
        )

    if prediction.get("confidence_reasons"):
        st.caption("Razones de confianza")
        st.write(", ".join(prediction["confidence_reasons"]))

    insight_col, comparable_col = st.columns([1, 1.25])
    with insight_col:
        if prediction.get("top_feature_effects"):
            with st.container(border=True):
                st.caption("Variables mas influyentes en esta prediccion")
                effects_df = pd.DataFrame(prediction["top_feature_effects"])
                st.dataframe(effects_df, use_container_width=True, hide_index=True)
        elif prediction.get("model_level_shap_summary"):
            with st.container(border=True):
                st.caption("No hubo explicacion local; se muestra SHAP global del modelo")
                shap_df = pd.DataFrame(prediction["model_level_shap_summary"])
                st.dataframe(shap_df, use_container_width=True, hide_index=True)

    with comparable_col:
        if prediction.get("comparables"):
            with st.container(border=True):
                st.caption("Comparables sugeridos")
                _render_comparable_cards(prediction["comparables"][:6])
        else:
            with st.container(border=True):
                st.caption("Comparables sugeridos")
                st.info("Todavia no encontramos comparables suficientemente cercanos para este caso.")


def main() -> None:
    st.set_page_config(
        page_title="Estimador de precio de vehiculos",
        page_icon=":car:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(194, 165, 120, 0.16), transparent 30%),
                    linear-gradient(180deg, #f5f1e8 0%, #fbf8f2 42%, #fffdf9 100%);
            }
            .block-container {
                max-width: 1240px;
                padding-top: 1.5rem;
                padding-bottom: 3rem;
            }
            div[data-testid="stMetric"] {
                background: rgba(255, 255, 255, 0.78);
                border: 1px solid rgba(87, 63, 35, 0.08);
                border-radius: 18px;
                padding: 0.9rem 1rem;
                box-shadow: 0 8px 24px rgba(77, 56, 31, 0.05);
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: rgba(255, 252, 247, 0.84);
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(71, 52, 28, 0.05);
            }
            button[kind="primary"] {
                border-radius: 14px;
                min-height: 3rem;
            }
            .result-card {
                border-radius: 20px;
                padding: 0.8rem 0.9rem;
                min-height: 7.5rem;
                border: 1px solid rgba(92, 63, 31, 0.08);
                box-shadow: 0 10px 26px rgba(77, 56, 31, 0.06);
                background: rgba(255, 253, 249, 0.88);
            }
            .result-card-primary {
                background: linear-gradient(145deg, #fff3d9 0%, #fffaf0 100%);
            }
            .result-card-success {
                background: linear-gradient(145deg, #eef8ef 0%, #fbfffb 100%);
            }
            .result-card-warning {
                background: linear-gradient(145deg, #fff5e9 0%, #fffdf9 100%);
            }
            .result-card-title {
                font-size: 0.82rem;
                color: #6d5a45;
                margin-bottom: 0.25rem;
            }
            .result-card-value {
                font-size: 1.35rem;
                line-height: 1.15;
                font-weight: 700;
                color: #22170e;
                margin-bottom: 0.3rem;
            }
            .result-card-subtitle {
                font-size: 0.8rem;
                color: #74665a;
            }
            .comparable-card {
                border-radius: 18px;
                padding: 0.75rem 0.85rem;
                margin-bottom: 0.5rem;
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(87, 63, 35, 0.08);
            }
            .comparable-title {
                font-size: 0.94rem;
                font-weight: 700;
                color: #20150c;
                margin-bottom: 0.25rem;
            }
            .comparable-price {
                font-size: 1rem;
                font-weight: 700;
                color: #8c5b1e;
                margin-bottom: 0.2rem;
            }
            .comparable-meta {
                font-size: 0.78rem;
                color: #6b6257;
                margin-bottom: 0.15rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Estimador de precio de mercado de vehiculos usados")
    st.caption("Fuente unica: anuncios observables de Mercado Libre Colombia.")

    with st.sidebar:
        st.header("Configuracion")
        base_url = st.text_input("API base URL", value=DEFAULT_API_BASE_URL)
        api_connected = False
        try:
            active_models = load_active_models(base_url)
            st.success("API conectada")
            api_connected = True
            for item in active_models.get("items", []):
                st.write(
                    f"**{item['model_scope'].title()}**: {item['model_name']} ({item['algorithm']}) | "
                    f"MAE={float(item['metrics'].get('mae', 0)):,.0f}"
                )
        except Exception as exc:
            st.error(f"No se pudo cargar /predictions/models/active: {exc}")
            st.caption(
                "La aplicacion seguira disponible. Si la API esta arriba, todavia puedes usar el explorador "
                "y probar predicciones; solo faltara el panel de modelos activos."
            )

        st.info(
            "Las predicciones mainstream son hoy las mas robustas. "
            "Las predicciones para marcas no mainstream usan el modelo global y deben leerse con mas cautela."
        )

    if not api_connected:
        st.warning(
            "No se pudo leer el panel de modelos activos. Verifica la API o vuelve a cargar la pagina "
            "despues de reiniciar uvicorn."
        )

    explorer_tab, estimator_tab = st.tabs(["Explorador", "Estimador"])
    with explorer_tab:
        render_market_explorer(base_url)
    with estimator_tab:
        render_estimator(base_url)


if __name__ == "__main__":
    main()
