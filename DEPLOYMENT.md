# Deployment Guide for Learn2Master

This guide provides instructions for deploying the Learn2Master AI-Enabled Mastery Learning System in a production environment.

## Infrastructure Requirements
- **Container Orchestration**: Docker and Docker Compose (or Kubernetes).
- **Database**: SQLite (default, stored in `learn2master.db`) or a production SQL database (PostgreSQL/MySQL) via `DATABASE_URL`.
- **Reverse Proxy**: Nginx or Traefik recommended to handle SSL termination (though `Flask-Talisman` handles HSTS/Security headers).

## Environment Variables
The following variables should be set in production:

| Variable | Description | Recommended Value |
| --- | --- | --- |
| `SECRET_KEY` | Flask security key | A long, random string. |
| `DATABASE_URL` | DB connection string | `postgresql://user:pass@host/db` |
| `FLASK_DEBUG` | Debug mode | `False` |
| `PORT` | Application port | Automatically set by host (Render defaults to 10000) |

## Render Deployment (Recommended)
Learn2Master is optimized for Render as a single **Web Service**. You do not need a separate frontend deployment as Flask serves static assets via WhiteNoise.

### Configuration Settings:
- **Runtime**: `Python`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 4 app:app`

### Persistence (Crucial for SQLite):
If you use the default SQLite database on Render, **you must attach a Disk**. Otherwise, your data will be deleted every time the service restarts or redeploys.
1. In Render Dashboard, go to **Disks**.
2. Create a Disk with name `learn2master-data`.
3. Mount Path: `/app/instance` (Ensure your app is configured to look here).
   - *Note: Our default path is `/app/learn2master.db`. For Render Disks, you may need to update `database.py` or `config.py` to use the mounted path.*

### Database Setup on Render:
1. Create a **Render PostgreSQL** instance (Highly Recommended over SQLite).
2. Copy the **Internal Database URL**.
3. Add it as an environment variable named `DATABASE_URL` in your Web Service settings.
4. **Initialization**: Run the initialization script once via the Render Shell:
   ```bash
   python init_db.py
   python seed_data.py
   ```

## First-Time Deployment Checklist
1. Create the Web Service on Render.
2. Configure Environment Variables (`SECRET_KEY`, `DATABASE_URL`, etc.).
3. Deploy the service.
4. Open the **Shell** in the Render Dashboard and run:
   ```bash
   python init_db.py
   python seed_data.py
   ```

## Troubleshooting
### Error: `sqlite3.OperationalError: no such table: users`
This error occurs when the database schema has not been initialized.
- **Solution**: Open the Render Shell for your service and run `python init_db.py`.
- **Warning**: If you are not using a Render Disk and not using PostgreSQL, you will have to do this after every redeploy. Use **Render PostgreSQL** to avoid this.

## Docker Deployment
1. Build the image:
   ```bash
   docker build -t learn2master:latest .
   ```
2. Run the container:
   ```bash
   docker run -d -p 5000:5000 \
     -e SECRET_KEY="your-secure-key" \
     -v learn2master_data:/app/instance \
     learn2master:latest
   ```

## Database Migrations
If you modify the database schema (`models.py`), use the following commands to manage migrations:

1. Generate a new migration:
   ```bash
   flask db migrate -m "Description of change"
   ```
2. Apply migrations:
   ```bash
   flask db upgrade
   ```

## Monitoring & Health
- **Health Endpoint**: `GET /health` returns `{"status": "healthy"}`.
- **Logs**: Application logs are stored in `logs/learn2master.log` with automatic rotation.
- **Docker Healthcheck**: Included in the Dockerfile; monitors the `/health` endpoint every 30s.

## Security Features
- **Rate Limiting**: Brute-force protection on Login (5 req/min) and Assessment (10 req/min).
- **Security Headers**: HSTS, CSP, and XSS protection enabled via Talisman.
- **Static Assets**: Served efficiently via WhiteNoise with compression support.
