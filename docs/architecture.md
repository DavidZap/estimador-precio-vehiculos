# Arquitectura General

## 1. Objetivo del sistema

Construir un producto analitico que capture anuncios de Mercado Libre Colombia, mantenga historico de inventario y precios, entrene modelos de regresion y exponga:

- un modulo exploratorio del mercado capturado
- un modulo estimador de precio con rango, comparables y explicabilidad

## 2. Principios de arquitectura

- Fuente unica de mercado: Mercado Libre Colombia.
- Separacion estricta entre adquisicion, procesamiento, entrenamiento y serving.
- Persistencia de evidencia raw por anuncio y por corrida.
- Reproducibilidad de datasets y modelos.
- Desacople del conector de extraccion para soportar cambios en la fuente.
- Simplicidad operativa por encima de sofisticacion temprana.

## 3. Arquitectura por capas

### Dominio

Define entidades y reglas centrales:

- `Listing`: anuncio observado en Mercado Libre.
- `VehicleCanonical`: representacion canonica del vehiculo inferido desde varios anuncios.
- `PriceSnapshot`: observacion de precio de un anuncio en un momento del tiempo.
- `FeatureVector`: features derivadas para modelado.
- `ModelVersion`: artefacto entrenado y evaluado.
- `PredictionRequest` y `PredictionResult`.

### Aplicacion

Casos de uso:

- capturar inventario
- normalizar y homologar listings
- deduplicar
- generar features
- entrenar y evaluar modelos
- promover modelo productivo
- predecir precio
- recuperar comparables

### Infraestructura

Implementaciones concretas:

- conector Mercado Libre Colombia
- repositorios Postgres/Supabase
- almacenamiento raw en Supabase Storage o filesystem local
- artefactos de modelos en Storage/local
- jobs por CLI y GitHub Actions

### Presentacion

- API REST con FastAPI
- frontend MVP con Streamlit
- version futura robusta con Next.js

### Pipelines

- `extract`
- `raw_to_staging`
- `staging_to_processed`
- `train`
- `evaluate_and_promote`
- `batch_monitoring`

## 4. Flujo end-to-end

1. Un job ejecuta el conector de Mercado Libre.
2. Cada respuesta se guarda intacta en `raw` con metadata de corrida y timestamp.
3. Un pipeline transforma raw a tablas staging con esquema estable.
4. Un pipeline de calidad limpia, homologa y genera tablas processed/features.
5. Entrenamiento arma dataset versionado, compara modelos y registra metricas.
6. Solo se promueve el nuevo modelo si supera umbrales y al modelo activo.
7. FastAPI sirve exploracion, comparables y predicciones.
8. Streamlit consume la API y muestra mercado, distribuciones y estimador.

## 5. Arquitectura de despliegue

### MVP gratis

- `Frontend`: Streamlit Community Cloud o local.
- `API`: Render free / Railway low-cost / local Docker.
- `DB`: Supabase Postgres.
- `Storage`: Supabase Storage.
- `Jobs`: GitHub Actions para CI y tareas manuales; extraccion programada inicialmente local o runner propio barato.
- `Model registry`: tabla Postgres + archivos en Storage.

### Version escalable

- `Frontend`: Next.js en Vercel.
- `API`: FastAPI en Fly.io, Railway o contenedor dedicado.
- `Orquestacion`: Prefect server self-hosted o cloud economico.
- `Feature store light`: Postgres + Parquet particionado.
- `Monitoreo`: Evidently + dashboards + alertas.

## 6. Recomendacion de stack

### MVP gratis

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy + Alembic
- Supabase Postgres
- Supabase Storage
- DuckDB + Parquet
- pandas / polars
- scikit-learn
- CatBoost
- LightGBM o XGBoost
- SHAP
- Streamlit
- Docker Compose
- GitHub Actions

### Version escalable

- Mantener Python/FastAPI/Postgres
- Next.js para frontend
- Prefect para orquestacion
- dbt opcional para transformaciones SQL reproducibles
- Feast no es necesario al inicio; podria evaluarse despues

## 7. Decisiones clave y trade-offs

### Entidad anuncio vs vehiculo canonico

- `Listing` representa una publicacion puntual.
- `VehicleCanonical` representa el vehiculo estandarizado inferido.
- Trade-off: construir entidad canonica agrega complejidad, pero evita contaminar el modelo con textos y etiquetas inconsistentes.

### CatBoost como candidato principal

- Ventaja: maneja categoricas y faltantes muy bien.
- Trade-off: algo mas lento que un baseline lineal, pero mucho mas robusto para este dominio.

### Streamlit para MVP

- Ventaja: mas rapido y barato que Next.js para validar.
- Trade-off: menor flexibilidad visual y de escalamiento frontend.

### Registro de modelos ligero

- Ventaja: evita complejidad de MLflow en cloud free tier.
- Trade-off: menos funcionalidades out-of-the-box; se compensa con tablas de metadatos y versionado de artefactos.

## 8. Recomendacion de frontend para el MVP

Recomiendo `Streamlit`.

Motivos:

- velocidad de implementacion
- excelente para analitica exploratoria y filtros
- despliegue simple y barato
- integra graficas y tablas sin sobrecosto de backend BFF

Cuando el producto necesite mejor SEO, autenticacion compleja o UX mas rica, migrar a `Next.js` manteniendo FastAPI como backend.

## 9. Recomendacion de estrategia de extraccion

Orden recomendado:

1. Intentar APIs publicas/endpoint JSON de Mercado Libre Colombia si entregan datos suficientes y consistentes.
2. Usar scraping HTML/JSON embebido solo para completar campos faltantes.
3. Encapsular ambos mecanismos en una interfaz unica `MarketplaceConnector`.

Reglas:

- guardar siempre payload raw y metadata de extraccion
- no acoplar la logica de negocio al HTML
- versionar el parser por fuente y version
- registrar campos faltantes y calidad por corrida

## 10. Frecuencias recomendadas

- Extraccion incremental: 2 a 4 veces al dia en MVP.
- Procesamiento: despues de cada extraccion.
- Reentrenamiento: semanal al inicio, o antes si entra suficiente nueva data.
- Monitoreo de drift: diario o por cada reentrenamiento.
