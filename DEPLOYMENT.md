# Deployment Guide for Learn2Master

This guide provides instructions for deploying the Learn2Master AI-Enabled Mastery Learning System in a production environment.

## Infrastructure Requirements
- **Container Orchestration**: Docker and Docker Compose (or Kubernetes).
- **Database**: SQLite (default, stored as `learn2master.db` in the app root) or a production PostgreSQL database (e.g. Supabase/Render) via `DATABASE_URL`.
- **Reverse Proxy**: Nginx or Traefik recommended to handle SSL termination (though `Flask-Talisman` handles HSTS/Security headers).

## Environment Variables
The following variables should be set in production:

| Variable | Description | Recommended Value |
| --- | --- | --- |
| `LEARN2MASTER_SECRET_KEY` | Flask security key. **Required in production** — the app refuses to start without it (falls back to an insecure dev key only when `LEARN2MASTER_DEBUG=1`). `SECRET_KEY` is also accepted as an alias. | A long, random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`). |
| `DATABASE_URL` | DB connection string. Omit to use in-container SQLite (ephemeral). | `postgresql://user:pass@host/db` |
| `LEARN2MASTER_DEBUG` | Debug mode | `0` |
| `LEARN2MASTER_CSRF_ENABLED` | CSRF protection toggle | `1` |
| `PORT` | Application port | Automatically set by host (Render defaults to 10000) |

## Render Deployment (Recommended)
Learn2Master is optimized for Render as a single **Web Service**. You do not need a separate frontend deployment as Flask serves static assets via WhiteNoise.

### Configuration Settings:
- **Runtime**: `Python`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 4 app:app`

### Database Setup on Render:
1. Create a **Render PostgreSQL** instance.
2. Copy the **Internal Database URL**.
3. Add it as an environment variable named `DATABASE_URL` in your Web Service settings.
4. Initialize the schema and seed the demo data once via the Render Shell:
   ```bash
   python init_db.py && python seed_data.py
   ```

## Docker Deployment
The image runs `docker-entrypoint.sh`, which initializes the schema (when missing)
and seeds the reference data exactly once before Gunicorn starts. No build-time
database steps are required.

1. Build the image:
   ```bash
   docker build -t learn2master:latest .
   ```
2. Run the container (Postgres recommended so data persists outside the container):
   ```bash
   docker run -d -p 5000:5000 \
     -e LEARN2MASTER_SECRET_KEY="your-secure-key" \
     -e DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
     learn2master:latest
   ```
   Or with Docker Compose (reads `SECRET_KEY` / `DATABASE_URL` from your shell or a local `.env`):
   ```bash
   SECRET_KEY="your-secure-key" docker compose up -d
   ```
   > Note: without a `DATABASE_URL`, the container uses an in-container SQLite file
   > that is **not** persisted across container recreation.

## Database Schema
The schema is defined in `database_v2.sql` and applied by `init_db.py`. The
application also auto-initializes an empty database on first boot. To change the
schema, edit `database_v2.sql` and re-run `python init_db.py` against a fresh
database.

## Monitoring & Health
- **Health Endpoint**: `GET /health` returns `{"status": "ok", "database": "ok"}` (HTTP 200), or `{"status": "degraded", ...}` with HTTP 503 if the database probe fails.
- **Logs**: Application logs are stored in `logs/learn2master.log` with automatic rotation.
- **Docker Healthcheck**: Included in the Dockerfile; monitors the `/health` endpoint every 30s.

## Security Features
- **Rate Limiting**: Brute-force protection on Login (5 req/min) and Assessment (10 req/min).
- **Security Headers**: HSTS, CSP, and XSS protection enabled via Talisman.
- **Static Assets**: Served efficiently via WhiteNoise with compression support.
