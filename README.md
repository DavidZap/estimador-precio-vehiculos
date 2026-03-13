# Estimador de Precio de Mercado de Vehiculos Usados

Aplicacion analitica end-to-end para estimar precios observables de mercado de vehiculos usados en Colombia usando exclusivamente anuncios de Mercado Libre Colombia.

El sistema combina:

- captura y versionado de inventario de mercado
- normalizacion y enriquecimiento geografico
- modelos de machine learning para estimacion de precio
- API en FastAPI para exploracion y prediccion
- frontend MVP en Streamlit para explorador de mercado y estimador

La documentacion de arquitectura, roadmap y diseno por fases vive en `docs/`.

## Que hace hoy el proyecto

Actualmente el desarrollo ya permite:

- extraer anuncios desde Mercado Libre Colombia con estrategia resiliente
- guardar evidencia raw de cada corrida
- procesar anuncios desde `raw` hasta `staging` y `core`
- mantener historico de precios y estado del anuncio
- consultar inventario capturado por marca, modelo, ubicacion, ano, kilometraje y mas
- entrenar modelos de pricing para alcance global y para marcas mainstream
- servir predicciones por API con rango, confianza, comparables y explicabilidad
- consumir esa API desde un frontend MVP en Streamlit

## Fuente de datos

La fuente unica y obligatoria es Mercado Libre Colombia.

La extraccion sigue esta estrategia:

1. intenta API publica o endpoints accesibles
2. si hay bloqueo o `403`, usa fallback web
3. si la pagina requiere JavaScript, usa navegador automatizado con Playwright
4. guarda siempre evidencia raw y metadatos de extraccion

## Arquitectura resumida

Capas principales:

- `domain`: entidades y contratos de negocio
- `application`: servicios y casos de uso
- `infrastructure`: base de datos, conectores, ML serving, almacenamiento
- `pipelines`: extraccion, procesamiento, entrenamiento y monitoreo
- `api`: endpoints FastAPI
- `frontend`: app Streamlit

Persistencia:

- `raw`: payloads originales y corridas de extraccion
- `staging`: anuncios parseados para normalizacion
- `core`: inventario limpio, historico, features y comparables
- `ml`: registro de modelos y artefactos
- `ops`: ejecuciones y auditoria operativa

## Modelos de prediccion

Hoy el serving usa dos alcances:

- `mainstream`: para `Toyota`, `Mazda`, `Renault`, `Chevrolet`, `Volkswagen`
- `global`: fallback para cualquier otra marca o segmento con menor cobertura

Consideraciones de negocio:

- las predicciones `mainstream` son las mas fuertes y estables del sistema
- las predicciones para vehiculos no mainstream dependen del modelo `global`
- el modelo `global` es util como referencia inicial de mercado, pero hoy tiene menor precision y debe leerse con mas cautela
- para vehiculos no mainstream conviene apoyar la salida del modelo con comparables observables y criterio humano

La respuesta de prediccion incluye:

- precio estimado
- rango estimado
- score y etiqueta de confianza
- modelo y scope usados
- comparables
- explicabilidad local o resumen SHAP del modelo

## API disponible

Endpoints principales:

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

Swagger:

- [http://localhost:8000/docs](http://localhost:8000/docs)

## Frontend MVP

El frontend MVP en Streamlit tiene dos modulos:

- explorador de mercado
- estimador de precio

En el explorador puedes:

- filtrar inventario capturado
- revisar distribucion de precios
- inspeccionar anuncios capturados

En el estimador puedes:

- ingresar caracteristicas del vehiculo
- obtener precio estimado y rango
- ver confianza y comparables
- revisar variables influyentes

El explorador ahora incluye:

- panorama del segmento con distribucion y ranking visible de marcas/modelos
- geografia interactiva con mapa por volumen o precio mediano
- inventario filtrable por zona desde la tabla geografica

## Ejecucion local con Supabase

Ruta recomendada cuando no usas Docker.

1. Crea `.env`:

```powershell
Copy-Item .env.example .env
```

2. Configura la conexion Postgres de Supabase:

```env
DATABASE_URL=postgresql+psycopg://postgres:[YOUR_PASSWORD]@[YOUR_SUPABASE_HOST]:5432/postgres
DATABASE_SSL_MODE=require
```

3. Instala dependencias:

```powershell
python -m pip install -e .[dev]
```

4. Inicializa base:

```powershell
python scripts/check_db_connection.py
python scripts/init_db.py
```

5. Levanta la API:

```powershell
python -m uvicorn vehicle_price_estimator.api.main:app --reload
```

6. Levanta el frontend:

```powershell
streamlit run src/vehicle_price_estimator/frontend/streamlit_app/Home.py
```

Por defecto Streamlit apunta a:

```text
http://localhost:8000/api/v1
```

Tambien puedes definirla por entorno:

```env
STREAMLIT_API_BASE_URL=http://localhost:8000/api/v1
```

## Flujo operativo tipico

1. extraer inventario
2. procesar `raw -> staging`
3. procesar `staging -> core`
4. entrenar o reentrenar modelos
5. promover modelos por scope
6. consumir la API y el frontend

## Scripts utiles

Base de datos:

- `python scripts/init_db.py`
- `python scripts/check_db_connection.py`

Extraccion y procesamiento:

- `python scripts/extract_marketplace.py --query "mazda 3 bogota" --limit 10`
- `python scripts/process_raw_to_staging.py`
- `python scripts/process_staging_to_processed.py`
- `python scripts/run_inventory_capture.py --dry-run`

Entrenamiento:

- `python scripts/train_models.py`
- `python scripts/train_models.py --min-model-rows 15 --no-promote`
- `python scripts/train_models.py --brands Toyota,Mazda,Renault,Chevrolet,Volkswagen --min-model-rows 15 --no-promote`

Promocion:

- `python scripts/promote_model.py --latest-scope global`
- `python scripts/promote_model.py --latest-scope mainstream`
- `python scripts/promote_model.py --registry-id TU_UUID --force`

## Docker

Docker es opcional. Si tu equipo no tiene virtualizacion habilitada, puedes trabajar sin problema con Supabase como base remota.

## Despliegue MVP

Ruta recomendada de costo bajo:

- backend API en Render
- base de datos en Supabase
- frontend en Streamlit Community Cloud o contenedor ligero

Archivos incluidos:

- `render.yaml`
- `infra/docker/Dockerfile.api`
- `infra/docker/Dockerfile.streamlit`
- `.github/workflows/ci.yml`
- `docs/deployment.md`

Entrada sugerida del frontend desplegado:

```bash
streamlit run streamlit_app.py
```

Variable importante para el frontend:

```env
STREAMLIT_API_BASE_URL=https://TU_BACKEND/api/v1
```

## Notas

- Usa la conexion directa Postgres, no la URL de la API REST.
- Manten `DATABASE_SSL_MODE=require`.
- Usa `python -m playwright install chromium` para habilitar el fallback con navegador en la extraccion.
- Para mas detalle de arquitectura, decisiones, roadmap y despliegue, revisa la carpeta `docs/`.
