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

## Scripts disponibles

- `python scripts/init_db.py`
- `python scripts/check_db_connection.py`
- `python scripts/extract_marketplace.py`

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

## Nota sobre Supabase

- Usa la conexion directa Postgres, no la URL de la API REST.
- Mantén `DATABASE_SSL_MODE=require`.
- El endpoint `GET /api/v1/meta/settings` devuelve la URL enmascarada para confirmar que la configuracion cargó bien.

## Docker es opcional

Si tu equipo no tiene virtualizacion habilitada, puedes trabajar normalmente con Supabase y ejecutar toda esta fase sin Docker.
