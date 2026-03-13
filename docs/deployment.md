# Deployment Guide

## MVP deployment recommendation

### Backend API

- Service: Render Web Service
- Runtime: Python
- Start command:

```bash
python -m uvicorn vehicle_price_estimator.api.main:app --host 0.0.0.0 --port $PORT
```

- Health check:

```text
/health
```

### Database

- Service: Supabase Postgres
- Use the direct or pooled Postgres connection string
- Keep `DATABASE_SSL_MODE=require`

### Frontend

- Service: Streamlit Community Cloud or a second low-cost container service
- Entry point:

```bash
streamlit run streamlit_app.py
```

- Required environment variable:

```text
STREAMLIT_API_BASE_URL=https://YOUR_BACKEND_DOMAIN/api/v1
```

## Required environment variables

Backend:

- `APP_ENV=production`
- `APP_DEBUG=false`
- `API_PREFIX=/api/v1`
- `DATABASE_URL=postgresql+psycopg://...`
- `DATABASE_SSL_MODE=require`
- `RAW_STORAGE_PATH=/opt/render/project/src/data/raw`
- `ARTIFACTS_PATH=/opt/render/project/src/data/artifacts`

Frontend:

- `STREAMLIT_API_BASE_URL=https://YOUR_BACKEND_DOMAIN/api/v1`

## Post-deploy checklist

1. Check `GET /health`
2. Check `GET /api/v1/health/db`
3. Open Swagger at `/docs`
4. Confirm `GET /api/v1/predictions/models/active`
5. Test one mainstream and one non-mainstream prediction from the frontend

## Notes

- The `mainstream` model should be preferred for `Toyota`, `Mazda`, `Renault`, `Chevrolet`, and `Volkswagen`
- The `global` model remains a fallback and should be interpreted more cautiously
- Mercado Libre extraction is more reliable from environments that can run Playwright/Chromium
