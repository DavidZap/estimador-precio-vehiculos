# Modelo Relacional Inicial en Supabase/Postgres

## 1. Esquemas

- `raw`: evidencia original y corridas de extraccion
- `staging`: datos semi-normalizados
- `core`: entidades limpias y operativas
- `ml`: datasets, modelos y predicciones
- `ops`: auditoria, jobs y monitoreo

## 2. Tablas principales

### `raw.extract_runs`

Registra cada corrida de captura.

Campos sugeridos:

- `id` UUID PK
- `source_name` text not null default `mercadolibre_co`
- `connector_type` text not null
- `started_at` timestamptz not null
- `finished_at` timestamptz null
- `status` text not null
- `query_params` jsonb
- `items_discovered` int
- `items_persisted` int
- `error_count` int
- `notes` text

### `raw.listing_payloads`

Guarda la evidencia raw por anuncio observado.

- `id` bigserial PK
- `extract_run_id` UUID FK
- `source_listing_id` text not null
- `source_url` text not null
- `payload_json` jsonb
- `payload_html_path` text
- `payload_json_path` text
- `payload_hash` text not null
- `observed_at` timestamptz not null
- `http_status` int
- `parser_version` text
- `ingested_at` timestamptz default now()

Indices:

- unique parcial por `extract_run_id, source_listing_id`
- index por `source_listing_id`
- index por `observed_at`

### `staging.marketplace_listings`

Estructura intermedia estable.

- `id` bigserial PK
- `extract_run_id` UUID FK
- `source_listing_id` text not null
- `source_url` text not null
- `title_raw` text
- `description_raw` text
- `price_amount` numeric(14,2)
- `currency` text
- `location_raw` text
- `city_raw` text
- `state_raw` text
- `brand_raw` text
- `model_raw` text
- `version_raw` text
- `year_raw` int
- `mileage_raw` numeric(14,2)
- `fuel_raw` text
- `transmission_raw` text
- `vehicle_type_raw` text
- `color_raw` text
- `attributes_json` jsonb
- `published_at_source` timestamptz null
- `seller_type` text null
- `image_urls` jsonb
- `first_seen_at` timestamptz
- `last_seen_at` timestamptz

### `core.vehicle_canonical`

Representa el vehiculo homologado.

- `id` UUID PK
- `brand_std` text not null
- `model_std` text not null
- `version_std` text null
- `body_type_std` text null
- `fuel_type_std` text null
- `transmission_std` text null
- `year` int null
- `engine_std` text null
- `drivetrain_std` text null
- `canonical_key` text not null unique
- `created_at` timestamptz default now()

### `core.listings`

Anuncio limpio y vigente.

- `id` UUID PK
- `source_name` text not null
- `source_listing_id` text not null
- `vehicle_canonical_id` UUID FK
- `listing_fingerprint` text not null
- `title_clean` text
- `description_clean` text
- `price_amount` numeric(14,2)
- `currency` text
- `price_cop` numeric(14,2)
- `city_std` text
- `state_std` text
- `brand_std` text
- `model_std` text
- `version_std` text
- `year` int
- `mileage_km` numeric(14,2)
- `fuel_type_std` text
- `transmission_std` text
- `vehicle_type_std` text
- `color_std` text
- `published_at_source` timestamptz null
- `first_seen_at` timestamptz not null
- `last_seen_at` timestamptz not null
- `is_active` boolean not null default true
- `quality_score` numeric(5,2)
- `outlier_flag` boolean default false
- `raw_last_payload_id` bigint null
- `created_at` timestamptz default now()
- `updated_at` timestamptz default now()

Indices:

- unique `source_name, source_listing_id`
- index por `brand_std, model_std, year`
- index por `price_cop`
- index por `mileage_km`
- index por `city_std`

### `core.listing_price_history`

Historico de precios por anuncio.

- `id` bigserial PK
- `listing_id` UUID FK
- `observed_at` timestamptz not null
- `price_amount` numeric(14,2) not null
- `currency` text not null
- `price_cop` numeric(14,2) not null
- `status` text not null
- `extract_run_id` UUID FK
- unique `listing_id, observed_at`

### `core.listing_status_history`

Seguimiento de vida del anuncio.

- `id` bigserial PK
- `listing_id` UUID FK
- `observed_at` timestamptz not null
- `status` text not null
- `extract_run_id` UUID FK

Estados sugeridos:

- `active`
- `not_found`
- `removed`
- `sold_unknown`

### `core.listing_features`

Features para exploracion y ML.

- `listing_id` UUID PK FK
- `snapshot_date` date not null
- `vehicle_age` numeric(6,2)
- `km_per_year` numeric(14,2)
- `equipment_score` numeric(8,4)
- `version_rarity_score` numeric(8,4)
- `regional_market_score` numeric(8,4)
- `listing_age_days` numeric(10,2)
- `comparable_inventory_density` numeric(10,2)
- `title_embedding_ref` text null
- `text_flags_json` jsonb
- `feature_payload` jsonb

### `ml.training_datasets`

- `id` UUID PK
- `dataset_version` text unique not null
- `created_at` timestamptz not null
- `train_start_date` date
- `train_end_date` date
- `row_count` int
- `feature_list` jsonb
- `target_definition` text
- `filters_applied` jsonb
- `parquet_path` text
- `data_hash` text

### `ml.model_registry`

- `id` UUID PK
- `model_name` text not null
- `model_version` text not null
- `algorithm` text not null
- `dataset_id` UUID FK
- `artifact_path` text not null
- `metrics_json` jsonb not null
- `params_json` jsonb
- `feature_schema_json` jsonb
- `shap_artifact_path` text null
- `status` text not null
- `is_active` boolean not null default false
- `promoted_at` timestamptz null
- `created_at` timestamptz not null default now()

Estados:

- `trained`
- `validated`
- `rejected`
- `active`
- `archived`

### `ml.prediction_logs`

- `id` UUID PK
- `requested_at` timestamptz not null
- `model_registry_id` UUID FK
- `request_payload` jsonb not null
- `prediction_price_cop` numeric(14,2) not null
- `prediction_range_min_cop` numeric(14,2) not null
- `prediction_range_max_cop` numeric(14,2) not null
- `confidence_score` numeric(8,4) null
- `comparables_json` jsonb
- `explanations_json` jsonb

### `ops.pipeline_runs`

- `id` UUID PK
- `pipeline_name` text not null
- `started_at` timestamptz not null
- `finished_at` timestamptz null
- `status` text not null
- `context_json` jsonb
- `metrics_json` jsonb
- `error_json` jsonb

## 3. Relaciones clave

- Un `extract_run` produce muchos `listing_payloads`.
- Un `source_listing_id` puede tener muchos payloads observados en distintos momentos.
- Un `listing` tiene muchas observaciones de precio y de estado.
- Muchos `listings` pueden mapear al mismo `vehicle_canonical`.
- Un `training_dataset` produce muchos modelos candidatos.
- Un solo `model_registry` puede estar activo a la vez por entorno.

## 4. Estrategia de versionado de datos

- Raw inmutable por corrida.
- Staging regenerable desde raw.
- Processed regenerable desde staging + reglas versionadas.
- Datasets de entrenamiento congelados en Parquet con `dataset_version`.

## 5. Reglas iniciales de integridad

- Nunca sobrescribir raw.
- Nunca borrar historico de precios.
- Promocion de modelo solo si:
  - mejora MAE y/o MAPE respecto al activo
  - no viola reglas de estabilidad por segmento
  - pasa validaciones de features
