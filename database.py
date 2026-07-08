"""
database.py — Supabase/PostgreSQL connection layer for Learn2Master.

Replaces the original sqlite3 implementation. Uses psycopg2 with a
ThreadedConnectionPool so connections are safe under multi-threaded WSGI
servers (Gunicorn, uWSGI). Each Flask request borrows and returns a connection
rather than opening a new one on every call.

Environment variables (set in .env):
    DATABASE_URL      — Supabase PostgreSQL connection string (pooler, port 6543)
                        SSL is enforced automatically (sslmode=require injected
                        if not already present in the DSN).
    FLASK_SECRET_KEY  — Random hex string for Flask session signing
    SUPABASE_URL      — https://<ref>.supabase.co
    SUPABASE_SERVICE_KEY — service_role key (bypasses RLS for backend operations)
"""

import os
import threading
from typing import Optional
import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

# ── Connection pool — ThreadedConnectionPool for Gunicorn safety ─────────────
# Fix: SimpleConnectionPool is NOT thread-safe. ThreadedConnectionPool uses an
# internal lock so concurrent Gunicorn workers can borrow/return connections
# without race conditions.
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def _ensure_ssl(dsn: str) -> str:
    """Inject sslmode=require into the DSN if not already present.

    Supabase requires SSL. Without this, connections may be rejected in
    production or silently use an unencrypted channel.
    """
    if "sslmode=" in dsn:
        return dsn
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}sslmode=require"


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    # Double-checked locking: fast path skips the lock when pool is healthy
    if _pool is not None and not _pool.closed:
        return _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            if not DATABASE_URL:
                raise RuntimeError(
                    "DATABASE_URL environment variable is not set. "
                    "Create a .env file with your Supabase connection string."
                )
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=_ensure_ssl(DATABASE_URL),
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
    return _pool


def get_db():
    """
    Borrow a psycopg2 connection from the thread-safe pool.

    The returned connection uses RealDictCursor so row access matches the
    original sqlite3.Row dict-style access (row["column_name"]).

    IMPORTANT: Every caller must call release_db(conn) in a finally block.
    """
    conn = _get_pool().getconn()
    # Verify the connection is alive; replace silently if it has been dropped
    # by Supabase's idle timeout (~5 min on the pooler).
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        try:
            _get_pool().putconn(conn, close=True)
        except Exception:
            pass
        conn = _get_pool().getconn()
    return conn


def release_db(conn):
    """Return a connection to the pool. Call in every finally block."""
    if conn is not None:
        try:
            _get_pool().putconn(conn)
        except Exception:
            pass


def execute(conn, sql: str, params: tuple = ()):
    """
    Convenience wrapper — executes a query and returns the cursor.
    Caller is responsible for fetching results and committing writes.
    """
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur
