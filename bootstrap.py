"""First-boot database bootstrap.

Initializes the schema when the database is missing and seeds the initial
reference data exactly once (when the users table is empty). This runs before
the web server starts so that multiple Gunicorn workers do not race to create
the schema, and so the non-idempotent parts of the seed script never run twice.
"""
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap")


def _normalize(url):
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def main():
    from database import get_db
    import init_db

    user_count = None
    try:
        conn = get_db()
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        user_count = row[0]
        conn.close()
    except Exception:
        # Table (and likely the whole schema) does not exist yet.
        user_count = None

    if user_count is None:
        logger.info("No schema detected. Initializing database schema...")
        url = _normalize(os.environ.get("DATABASE_URL"))
        if url and url.startswith("postgresql://"):
            init_db.run_postgres(url)
        else:
            init_db.run_sqlite()
        user_count = 0

    if user_count == 0:
        logger.info("Empty database detected. Seeding initial data...")
        import seed_data  # noqa: F401  (seeding executes on import)
        logger.info("Seeding complete.")
    else:
        logger.info("Database already populated (%s users). Skipping seed.", user_count)


if __name__ == "__main__":
    main()
