# Roadmap por Fases

## Fase 0. Diseno base

Objetivo:

- dejar decisiones de arquitectura, datos y stack cerradas

Entregables:

- arquitectura
- modelo relacional
- estructura del repo
- roadmap

## Fase 1. Esqueleto del repositorio

Construir en este orden:

1. `src/` con arquitectura limpia
2. configuracion por entornos
3. API FastAPI base
4. modelos ORM y migraciones iniciales
5. Docker Compose local

## Fase 2. Conector Mercado Libre Colombia

Construir en este orden:

1. interfaz `MarketplaceConnector`
2. cliente de busqueda/listado
3. cliente de detalle
4. persistencia raw
5. pruebas de parser y tolerancia a cambios

## Fase 3. Pipelines raw -> staging -> processed

Construir en este orden:

1. parseo estable a staging
2. homologacion de marca/modelo/version/ubicacion
3. deduplicacion
4. historico de precios
5. features base y outliers

## Fase 4. Exploracion y consultas

Construir en este orden:

1. endpoints de inventario
2. filtros agregados
3. comparables
4. metricas y distribuciones

## Fase 5. Training pipeline

Construir en este orden:

1. dataset builder
2. baseline lineal
3. Random Forest
4. CatBoost
5. LightGBM o XGBoost
6. evaluacion y seleccion automatica
7. registro y promocion

## Fase 6. Serving de prediccion

Construir en este orden:

1. carga del modelo activo
2. endpoint de prediccion individual
3. rango estimado
4. explicabilidad
5. score de confianza

## Fase 7. Frontend MVP

Construir en este orden:

1. dashboard exploratorio
2. formulario de estimacion
3. vista de comparables
4. distribucion y explicaciones
5. optimizacion mobile

## Fase 8. Operacion y despliegue

Construir en este orden:

1. CI con GitHub Actions
2. despliegue cloud barato
3. jobs manuales/programados
4. monitoreo basico de datos y modelo

## Fase 9. Escalamiento

Evaluar despues del MVP:

- Next.js
- Prefect
- dashboards de drift
- embeddings de texto mas sofisticados
- procesamiento de imagenes

## Estructura de carpetas completa propuesta

```text
.
|-- README.md
|-- .env.example
|-- .gitignore
|-- docker-compose.yml
|-- Makefile
|-- pyproject.toml
|-- alembic.ini
|-- docs/
|   |-- architecture.md
|   |-- data-model.md
|   `-- roadmap.md
|-- infra/
|   |-- docker/
|   |-- sql/
|   `-- supabase/
|-- notebooks/
|-- scripts/
|   |-- extract_marketplace.py
|   |-- process_raw_to_staging.py
|   |-- process_staging_to_processed.py
|   |-- train_models.py
|   |-- promote_model.py
|   `-- backfill_price_history.py
|-- data/
|   |-- raw/
|   |-- staging/
|   |-- processed/
|   `-- artifacts/
|-- tests/
|   |-- unit/
|   |-- integration/
|   `-- fixtures/
`-- src/
    `-- vehicle_price_estimator/
        |-- __init__.py
        |-- config/
        |   |-- settings.py
        |   `-- logging.py
        |-- domain/
        |   |-- entities/
        |   |-- value_objects/
        |   |-- services/
        |   `-- repositories/
        |-- application/
        |   |-- dto/
        |   |-- use_cases/
        |   `-- services/
        |-- infrastructure/
        |   |-- db/
        |   |   |-- models/
        |   |   |-- repositories/
        |   |   `-- migrations/
        |   |-- storage/
        |   |-- connectors/
        |   |   `-- mercadolibre/
        |   |       |-- client.py
        |   |       |-- parser.py
        |   |       |-- models.py
        |   |       `-- connector.py
        |   |-- ml/
        |   |   |-- features/
        |   |   |-- training/
        |   |   |-- inference/
        |   |   `-- registry/
        |   `-- observability/
        |-- pipelines/
        |   |-- extraction/
        |   |-- processing/
        |   |-- training/
        |   `-- monitoring/
        |-- api/
        |   |-- main.py
        |   |-- deps.py
        |   |-- routers/
        |   |-- schemas/
        |   `-- services/
        `-- frontend/
            `-- streamlit_app/
                |-- Home.py
                |-- pages/
                `-- components/
```

## Orden exacto de construccion recomendado

1. Esqueleto del repo y configuracion.
2. Modelo de datos y migraciones.
3. Conector de extraccion y persistencia raw.
4. Normalizacion y deduplicacion.
5. Consultas exploratorias API.
6. Dataset builder y entrenamiento.
7. Serving y explicabilidad.
8. Frontend MVP.
9. CI/CD y despliegue.
