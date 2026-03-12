from __future__ import annotations

from decimal import Decimal

import httpx
import pandas as pd
import streamlit as st


DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"
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


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_reasonable_option(value: str, *, field_name: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(token in lowered for token in BANNED_OPTION_TOKENS):
        return False
    if field_name == "brand":
        return normalized in KNOWN_BRANDS
    if field_name == "engine":
        try:
            numeric = float(normalized.replace(",", "."))
            return 0.6 <= numeric <= 8.0
        except ValueError:
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


def _select_with_default(label: str, options: list[str], default: str | None = None, key: str | None = None) -> str:
    normalized_options = [""] + sorted({option for option in options if option})
    if default and default not in normalized_options:
        normalized_options.append(default)
    normalized_options = [""] + sorted({option for option in normalized_options if option})
    index = 0
    if default and default in normalized_options:
        index = normalized_options.index(default)
    return st.selectbox(label, normalized_options, index=index, key=key)


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
    sidebar_filters: dict[str, str | int | bool | None] = {}

    brands = [""] + [str(item["value"]) for item in filters_payload.get("brands", [])]
    selected_brand = st.sidebar.selectbox("Marca", brands, index=0)
    if selected_brand:
        sidebar_filters["brand"] = selected_brand

    models = [""] + [str(item["value"]) for item in filters_payload.get("models", [])]
    selected_model = st.sidebar.selectbox("Modelo", models, index=0)
    if selected_model:
        sidebar_filters["model"] = selected_model

    years = [item["value"] for item in filters_payload.get("years", []) if isinstance(item.get("value"), int)]
    min_year = int(min(years)) if years else 2010
    max_year = int(max(years)) if years else 2026
    selected_year_range = st.sidebar.slider("Rango de ano", min_year, max_year, (min_year, max_year))
    sidebar_filters["year_min"] = selected_year_range[0]
    sidebar_filters["year_max"] = selected_year_range[1]

    departments = [""] + [str(item["value"]) for item in filters_payload.get("departments", [])]
    selected_department = st.sidebar.selectbox("Departamento", departments, index=0)
    if selected_department:
        sidebar_filters["department"] = selected_department

    municipalities = [""] + [str(item["value"]) for item in filters_payload.get("municipalities", [])]
    selected_municipality = st.sidebar.selectbox("Municipio", municipalities, index=0)
    if selected_municipality:
        sidebar_filters["municipality"] = selected_municipality

    transmissions = [""] + [str(item["value"]) for item in filters_payload.get("transmissions", [])]
    selected_transmission = st.sidebar.selectbox("Transmision", transmissions, index=0)
    if selected_transmission:
        sidebar_filters["transmission"] = selected_transmission

    fuel_types = [""] + [str(item["value"]) for item in filters_payload.get("fuel_types", [])]
    selected_fuel = st.sidebar.selectbox("Combustible", fuel_types, index=0)
    if selected_fuel:
        sidebar_filters["fuel_type"] = selected_fuel

    include_outliers = st.sidebar.toggle("Incluir outliers", value=False)
    sidebar_filters["outlier_flag"] = None if include_outliers else False
    sidebar_filters["is_active"] = True

    display_filters = {
        "Marca": selected_brand or "Todas",
        "Modelo": selected_model or "Todos",
        "Ano": f"{selected_year_range[0]} - {selected_year_range[1]}",
        "Departamento": selected_department or "Todos",
        "Municipio": selected_municipality or "Todos",
        "Transmision": selected_transmission or "Todas",
        "Combustible": selected_fuel or "Todos",
    }
    return sidebar_filters, display_filters


def render_market_explorer(base_url: str) -> None:
    filters_payload = load_filters(base_url)
    query_filters, display_filters = _build_market_filters(filters_payload)

    st.subheader("Explorador de mercado")
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
        st.caption("Distribucion de precios del segmento filtrado")
        st.bar_chart(chart_df, x="bucket", y="count", horizontal=True)

    listings = load_listings(base_url, {**query_filters, "page": 1, "page_size": 25})
    listing_items = listings.get("items", [])
    if listing_items:
        st.caption("Inventario capturado")
        listing_df = pd.DataFrame(listing_items)
        columns = [
            "brand_std",
            "model_std",
            "trim_std",
            "year",
            "mileage_km",
            "price_cop",
            "department_std",
            "municipality_std",
            "locality_std",
            "source_url",
        ]
        available_columns = [column for column in columns if column in listing_df.columns]
        st.dataframe(listing_df[available_columns], use_container_width=True, hide_index=True)
    else:
        st.info("No hay anuncios para los filtros seleccionados.")


def render_estimator(base_url: str) -> None:
    st.subheader("Estimador de precio")
    st.caption(
        "Las marcas mainstream usan el modelo mas fuerte del sistema. "
        "Las marcas no mainstream usan el modelo global y deben interpretarse con mayor cautela."
    )

    base_filters = load_filters(base_url, {"is_active": True, "outlier_flag": False})
    brands = _facet_values(base_filters, "brands", field_name="brand")
    departments = _facet_values(base_filters, "departments")
    col1, col2, col3 = st.columns(3)
    with col1:
        brand_std = _select_with_default("Marca", brands, default="Toyota", key="estimate_brand")
    with col3:
        department_std = _select_with_default(
            "Departamento",
            departments,
            default="Bogota D.C.",
            key="estimate_department",
        )

    model_filters = load_filters(
        base_url,
        {
            "brand": brand_std or None,
            "department": department_std or None,
            "is_active": True,
            "outlier_flag": False,
        },
    )
    with col2:
        model_std = _select_with_default(
            "Modelo",
            _facet_values(model_filters, "models", field_name="model"),
            default="Corolla Cross",
            key="estimate_model",
        )

    scoped_catalog = load_estimator_catalog(
        base_url,
        brand=brand_std or None,
        model=model_std or None,
        department=department_std or None,
        municipality=None,
    )
    scoped_filters = scoped_catalog["filters"]
    municipalities = _facet_values(scoped_filters, "municipalities", field_name="municipality")
    trims = scoped_catalog["trims"]
    engines = scoped_catalog["engines"]
    vehicle_types = scoped_catalog["vehicle_types"]
    transmission_options = _facet_values(scoped_filters, "transmissions", field_name="transmission")
    fuel_options = _facet_values(scoped_filters, "fuel_types", field_name="fuel_type")

    col4, col5, col6 = st.columns(3)
    year = col4.number_input("Ano", min_value=1950, max_value=2100, value=2022, step=1)
    mileage_km = col5.number_input("Kilometraje", min_value=0, value=42000, step=1000)
    with col6:
        engine_displacement_std = _select_with_default(
            "Motor",
            engines,
            default="2.0",
            key="estimate_engine",
        )

    col7, col8, col9 = st.columns(3)
    transmission_std = col7.selectbox("Transmision", [""] + transmission_options, index=0, key="estimate_transmission")
    fuel_type_std = col8.selectbox("Combustible", [""] + fuel_options, index=0, key="estimate_fuel")
    with col9:
        trim_std = _select_with_default("Trim", trims, default="XEI", key="estimate_trim")

    col10, col11, col12 = st.columns(3)
    with col10:
        municipality_std = _select_with_default(
            "Municipio",
            municipalities,
            default="Bogota D.C.",
            key="estimate_municipality",
        )

    locality_catalog = load_estimator_catalog(
        base_url,
        brand=brand_std or None,
        model=model_std or None,
        department=department_std or None,
        municipality=municipality_std or None,
    )
    locality_options = _facet_values(locality_catalog["filters"], "localities", field_name="locality")
    with col11:
        locality_std = _select_with_default(
            "Localidad",
            locality_options,
            default="Suba",
            key="estimate_locality",
        )
    with col12:
        vehicle_type_std = _select_with_default(
            "Tipo de vehiculo",
            vehicle_types,
            default=None,
            key="estimate_vehicle_type",
        )

    hybrid_flag = st.checkbox("Hibrido", value=fuel_type_std == "Hibrido")
    mhev_flag = st.checkbox("MHEV", value=False)
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

    result_cols = st.columns(4)
    result_cols[0].metric("Precio estimado", _format_cop(prediction["predicted_price_cop"]))
    result_cols[1].metric("Rango inferior", _format_cop(prediction["predicted_range_lower_cop"]))
    result_cols[2].metric("Rango superior", _format_cop(prediction["predicted_range_upper_cop"]))
    result_cols[3].metric("Confianza", prediction["confidence_label"].title(), f"{prediction['confidence_score']:.2f}")

    scope_used = prediction["model_scope_used"]
    is_mainstream = payload["brand_std"] in MAINSTREAM_BRANDS
    st.markdown(
        f"""
        **Modelo usado:** `{prediction['model_name']}` (`{prediction['algorithm']}`)  
        **Scope solicitado/usado:** `{prediction['model_scope_requested']}` -> `{scope_used}`  
        **Metodo de rango:** `{prediction['range_method_used']}`  
        **Comparables:** `{prediction['comparables_count']}` (`estrictos={prediction['strict_comparables_count']}`, `fallback={prediction['fallback_comparables_count']}`)  
        **Lectura recomendada:** `{'mainstream' if is_mainstream else 'global/no mainstream'}`
        """
    )

    if not is_mainstream or scope_used == "global":
        st.warning(
            "Esta prediccion usa el modelo global o pertenece a un segmento no mainstream. "
            "Tomala como una referencia de mercado inicial y apoyate mas en comparables y contexto."
        )

    if prediction.get("confidence_reasons"):
        st.caption("Razones de confianza")
        st.write(", ".join(prediction["confidence_reasons"]))

    if prediction.get("top_feature_effects"):
        st.caption("Variables mas influyentes en esta prediccion")
        effects_df = pd.DataFrame(prediction["top_feature_effects"])
        st.dataframe(effects_df, use_container_width=True, hide_index=True)
    elif prediction.get("model_level_shap_summary"):
        st.caption("No hubo explicacion local; se muestra SHAP global del modelo")
        shap_df = pd.DataFrame(prediction["model_level_shap_summary"])
        st.dataframe(shap_df, use_container_width=True, hide_index=True)

    if prediction.get("comparables"):
        st.caption("Comparables sugeridos")
        comparables_df = pd.DataFrame(prediction["comparables"])
        columns = [
            "brand_std",
            "model_std",
            "trim_std",
            "year",
            "mileage_km",
            "price_cop",
            "municipality_std",
            "locality_std",
            "source_url",
            "comparable_score",
        ]
        available_columns = [column for column in columns if column in comparables_df.columns]
        st.dataframe(comparables_df[available_columns], use_container_width=True, hide_index=True)


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
                background: linear-gradient(180deg, #f3efe7 0%, #fbf8f3 35%, #ffffff 100%);
            }
            .block-container {
                padding-top: 2rem;
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
