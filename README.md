# Estimador de Precio de Venta de Vehiculos Usados

Base ejecutable de la Fase 1 del proyecto para estimar precios observables de mercado de vehiculos usados en Colombia usando exclusivamente Mercado Libre Colombia.

El proyecto queda ahora preparado para usar `Supabase Postgres` como ruta principal de desarrollo cuando Docker no esta disponible.

## Que incluye esta fase

- Estructura modular del repositorio.
- Configuracion base en Python con `pyproject.toml`.
- API inicial con `FastAPI`.
- Conexion a Postgres optimizada para Supabase.
- Modelos ORM iniciales con SQLAlchemy 2.0.
- Scripts base para inicializar base de datos y extraccion.
- `docker-compose` para correr API + Postgres local.

## Arranque recomendado con Supabase

1. Crea un proyecto en Supabase.
2. Ve a `Project Settings > Database`.
3. Copia la cadena de conexion Postgres directa del proyecto.
4. Crea tu `.env`:

```powershell
Copy-Item .env.example .env
```

5. Edita `.env` y reemplaza:

```env
DATABASE_URL=postgresql+psycopg://postgres:[YOUR_PASSWORD]@[YOUR_SUPABASE_HOST]:5432/postgres
DATABASE_SSL_MODE=require
```

6. Instala dependencias:

```powershell
python -m pip install -e .[dev]
```

7. Verifica conexion:

```powershell
python scripts/check_db_connection.py
```

8. Crea schemas y tablas:

```powershell
python scripts/init_db.py
```

9. Ejecuta la API:

```powershell
python -m uvicorn vehicle_price_estimator.api.main:app --reload
```

La API quedara disponible en [http://localhost:8000/docs](http://localhost:8000/docs).

## Arranque local alternativo con Docker

Usa esta ruta solo si tu equipo soporta virtualizacion y Docker Desktop funciona correctamente.

1. Crear archivo de entorno:

```powershell
Copy-Item .env.example .env
```

2. Ajusta `.env` para usar Postgres local:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/vehicle_price_estimator
DATABASE_SSL_MODE=disable
```

3. Instalar dependencias:

```powershell
python -m pip install -e .[dev]
```

4. Levantar Postgres local:

```powershell
docker compose up -d postgres
```

5. Crear schemas y tablas:

```powershell
python scripts/init_db.py
```

6. Ejecutar la API:

```powershell
uvicorn vehicle_price_estimator.api.main:app --reload
```

## Endpoints iniciales

- `GET /health`
- `GET /api/v1/health/db`
- `GET /api/v1/meta/settings`
- `GET /api/v1/market/listings`
- `GET /api/v1/market/filters`
- `GET /api/v1/market/summary`
- `GET /api/v1/market/distribution`
- `GET /api/v1/market/comparables`
- `GET /api/v1/predictions/models/active`
- `POST /api/v1/predictions/estimate`

## Scripts disponibles

- `python scripts/init_db.py`
- `python scripts/check_db_connection.py`
- `python scripts/extract_marketplace.py`
- `python scripts/run_inventory_capture.py --dry-run`
- `python scripts/run_inventory_capture.py --campaign discovery --brands toyota,mazda,chevrolet --regions bogota,medellin,cali`
- `python scripts/train_models.py`
- `python scripts/promote_model.py --registry-id TU_UUID`
- `python scripts/promote_model.py --latest-scope global`
- `python scripts/promote_model.py --latest-scope mainstream`

## Extraccion inicial Mercado Libre Colombia

El conector actual usa esta estrategia:

1. intenta la API publica de busqueda de Mercado Libre
2. si la API responde `403` u otro estado no exitoso, intenta una busqueda web fallback
3. si la web simple devuelve un challenge JavaScript, intenta un fallback con navegador real usando Playwright
4. guarda siempre evidencia raw de la corrida en `data/raw`
5. registra cada payload tambien en la tabla `raw.listing_payloads`

Para habilitar el fallback con navegador real por primera vez:

```powershell
python -m pip install -e .[dev]
python -m playwright install chromium
```

Ejemplo:

```powershell
python scripts/extract_marketplace.py --query "mazda 3 bogota" --limit 10
```

Opcional, para evitar pedir detalle por item:

```powershell
python scripts/extract_marketplace.py --query "renault sandero" --limit 10 --no-details
```

## Procesamiento raw a staging

Una vez tengas una corrida raw con `browser_search` o `web_search`, puedes generar la tabla staging:

```powershell
python scripts/process_raw_to_staging.py
```

Tambien puedes procesar una corrida especifica:

```powershell
python scripts/process_raw_to_staging.py --extract-run-id TU_EXTRACT_RUN_ID
```

El pipeline actual de staging parsea desde el HTML renderizado de busqueda:

- `source_listing_id`
- `source_url`
- `title_raw`
- `price_amount`
- `location_raw`
- `city_raw`
- `state_raw`
- `brand_raw`
- `model_raw`
- `version_raw`
- `year_raw`
- `mileage_raw`
- `image_url`

## Procesamiento staging a core

El siguiente paso normaliza staging y construye entidades de negocio en `core`:

```powershell
python scripts/process_staging_to_processed.py
```

Tambien puedes procesar una corrida especifica:

```powershell
python scripts/process_staging_to_processed.py --extract-run-id TU_EXTRACT_RUN_ID
```

El pipeline actual crea o actualiza:

- `core.vehicle_canonical`
- `core.listings`
- `core.listing_price_history`
- `core.listing_status_history`
- `core.listing_features`

Incluye en esta primera version:

- normalizacion basica de marca, modelo, version y ubicacion
- deduplicacion por `source_name + source_listing_id`
- historico de precios por observacion
- historico de estado `active`
- features iniciales:
  - `vehicle_age`
  - `km_per_year`
  - `equipment_score`
  - `version_rarity_score`
  - `regional_market_score`
  - `listing_age_days`
  - `comparable_inventory_density`
  - `outlier_flag` basico por IQR de segmento

Refinamientos actuales de normalizacion en `core.listings` y `core.vehicle_canonical`:

- `trim_std`
- `engine_displacement_std`
- `engine_cc`
- `hybrid_flag`
- `mhev_flag`
- `variant_raw`
- `marketing_tokens_json`

Esto permite separar mejor:

- `Touring`, `Grand Touring`, `Prime`, `Sport`, `LX` como trim
- `2.0`, `1.6`, `2000cc` como motor
- `AT`, `MT`, `Mecanico`, `Automatica` como transmision
- `Hibrido` y `MHEV` como flags estructurados

## Construccion de inventario amplio

Antes del entrenamiento conviene ampliar el inventario con una campana nacional orientada a marcas, regiones y modelos descubiertos en Mercado Libre Colombia.

Cobertura por defecto de la campana:

- marcas: `Toyota`, `Mazda`, `Chevrolet`, `Volkswagen`, `Renault`, `BYD`, `Kia`, `Mercedes-Benz`, `BMW`, `Audi`, `Nissan`
- hubs regionales: `Bogota`, `Medellin`, `Cali`, `Barranquilla`, `Cartagena`, `Bucaramanga`, `Cucuta`, `Pereira`, `Villavicencio`, `Pasto`
- anos ancla para backfill: `2010`, `2014`, `2018`, `2022` y el ano actual

Campanas disponibles:

- `discovery`: consulta `marca + region` para descubrir modelos presentes en Mercado Libre
- `model_region`: consulta `marca + modelo + region` usando modelos ya descubiertos en la base
- `year_backfill`: consulta `marca + ano + region` para reforzar cobertura desde 2010
- `full`: combina discovery, model_region y year_backfill

Ejemplos:

```powershell
python scripts/run_inventory_capture.py --campaign discovery --dry-run
```

```powershell
python scripts/run_inventory_capture.py --campaign discovery --brands toyota,mazda,chevrolet --regions bogota,medellin,cali --max-queries 12
```

```powershell
python scripts/run_inventory_capture.py --campaign model_region --brands toyota,mazda --regions bogota,cali --max-models-per-brand 8
```

```powershell
python scripts/run_inventory_capture.py --campaign year_backfill --brands renault,kia,nissan --regions bogota,medellin,cali --max-queries 20
```

Recomendacion operativa para presupuesto bajo:

1. Ejecuta primero `discovery` por lotes pequenos.
2. Revisa `/api/v1/market/filters` o `core.listings` para validar cobertura de marcas/modelos.
3. Ejecuta `model_region` para profundizar marcas/modelos ya observados.
4. Ejecuta `year_backfill` para reforzar cobertura 2010+ antes del entrenamiento.

## Entrenamiento inicial

La primera version de la Fase 5 ya entrena y compara varios candidatos sobre `core.listings` + `core.listing_features`.

Incluye:

- `ElasticNet` como baseline lineal
- `RandomForestRegressor`
- `HistGradientBoostingRegressor` como booster tabular liviano
- `CatBoost`, `LightGBM` y `XGBoost` si estan instalados en el entorno

El pipeline:

1. construye un dataset reproducible en `data/artifacts/training/datasets`
2. hace split temporal 80/20 usando `first_seen_at` y `updated_at`
3. entrena candidatos con target `log1p(price_cop)`
4. calcula `MAE`, `RMSE`, `MAPE` y `R2`
5. registra cada candidato en `ml.model_registry`
6. promueve automaticamente el mejor solo si mejora al modelo activo

Ejecutar:

```powershell
python -m pip install -e .[dev]
python scripts/train_models.py
```

Si quieres incluir outliers o anuncios inactivos:

```powershell
python scripts/train_models.py --include-outliers --include-inactive
```

Para entrenar el modelo segmentado mainstream:

```powershell
python scripts/train_models.py --brands Toyota,Mazda,Renault,Chevrolet,Volkswagen --min-model-rows 15 --no-promote
```

Para promover el mejor global y el mejor mainstream por separado:

```powershell
python scripts/promote_model.py --latest-scope global
python scripts/promote_model.py --latest-scope mainstream
```

## Serving y prediccion

La Fase 6 agrega una capa de serving con doble modelo:

- `global`: fallback para cualquier marca con cobertura limitada
- `mainstream`: preferido para `Toyota`, `Mazda`, `Renault`, `Chevrolet`, `Volkswagen`

El router de prediccion usa la marca para decidir el scope solicitado y luego:

1. intenta usar el modelo activo del scope correcto
2. si no existe, usa el ultimo modelo registrado de ese scope
3. si el scope solicitado es `mainstream` y no hay modelo disponible, cae a `global`

Ejemplos:

```powershell
python -m uvicorn vehicle_price_estimator.api.main:app --reload
```

Consultar modelos activos:

```text
GET /api/v1/predictions/models/active
```

Estimar precio:

```text
POST /api/v1/predictions/estimate
```

Payload ejemplo:

```json
{
  "brand_std": "Toyota",
  "model_std": "Corolla Cross",
  "trim_std": "XEI",
  "year": 2022,
  "mileage_km": 42000,
  "engine_displacement_std": "2.0",
  "transmission_std": "Automatica",
  "fuel_type_std": "Hibrido",
  "department_std": "Bogotá D.C.",
  "municipality_std": "Bogota D.C.",
  "locality_std": "Suba",
  "hybrid_flag": true,
  "mhev_flag": false
}
```

La respuesta incluye:

- precio estimado en COP
- rango estimado
- score y etiqueta de confianza
- modelo usado y scope efectivo
- comparables
- explicacion SHAP local si el modelo lo soporta

## Nota sobre Supabase

- Usa la conexion directa Postgres, no la URL de la API REST.
- Mantén `DATABASE_SSL_MODE=require`.
- El endpoint `GET /api/v1/meta/settings` devuelve la URL enmascarada para confirmar que la configuracion cargó bien.

## Docker es opcional

Si tu equipo no tiene virtualizacion habilitada, puedes trabajar normalmente con Supabase y ejecutar toda esta fase sin Docker.
