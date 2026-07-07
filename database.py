"""
database.py — Supabase/PostgreSQL connection layer for Learn2Master.

Replaces the original sqlite3 implementation. Uses psycopg2 with a
SimpleConnectionPool so each Flask request borrows and returns a connection
rather than opening a new one on every call.

Environment variables (set in .env):
    DATABASE_URL      — Supabase PostgreSQL connection string (pooler, port 6543)
    FLASK_SECRET_KEY  — Random hex string for Flask session signing
    SUPABASE_URL      — https://<ref>.supabase.co
    SUPABASE_SERVICE_KEY — service_role key (bypasses RLS for backend operations)
"""

import os
from typing import Optional
import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

# ── Connection pool (1 min, 10 max connections) ──────────────────────────────
_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Create a .env file with your Supabase connection string."
            )
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


def get_db():
    """
    Borrow a psycopg2 connection from the pool.

    The returned connection uses RealDictCursor so row access matches the
    original sqlite3.Row dict-style access (row["column_name"]).

    IMPORTANT: Every caller must call release_db(conn) in a finally block,
    or use the get_db_ctx() context manager instead.
    """
    return _get_pool().getconn()


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
