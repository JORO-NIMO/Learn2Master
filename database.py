import logging
import sqlite3
import os
import re

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "learn2master.db")

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, parameters=None):
        # Convert ? to %s
        sql = sql.replace('?', '%s')
        # Convert last_insert_rowid() to lastval()
        sql = sql.replace('last_insert_rowid()', 'lastval()')

        # Filter out PRAGMA
        if sql.strip().upper().startswith("PRAGMA"):
            return self

        if parameters:
            self.cursor.execute(sql, parameters)
        else:
            self.cursor.execute(sql)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)

    @property
    def rowcount(self):
        return self.cursor.rowcount

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, parameters=None):
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        wrapper = PostgresCursorWrapper(cursor)
        return wrapper.execute(sql, parameters)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def cursor(self):
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(cursor)

def connect_to_postgres(db_url):
    if not psycopg2:
        return None

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    def try_connect(url):
        if "?" not in url:
            url += "?sslmode=require"
        elif "sslmode=" not in url:
            url += "&sslmode=require"
        return psycopg2.connect(url)

    try:
        return try_connect(db_url)
    except Exception as e:
        if "supabase.co" in db_url and (":5432" in db_url or "@db." in db_url):
            logging.warning("Supabase connection on port 5432 failed. Retrying with port 6543...")
            try:
                if ":5432" in db_url:
                    alt_url = db_url.replace(":5432", ":6543")
                else:
                    parts = db_url.split('/')
                    if len(parts) >= 3:
                        host_part = parts[2]
                        if "@" in host_part:
                            user_pass, host = host_part.split("@")
                            if ":" not in host:
                                parts[2] = f"{user_pass}@{host}:6543"
                                alt_url = "/".join(parts)
                            else:
                                alt_url = db_url
                        else:
                            alt_url = db_url
                    else:
                        alt_url = db_url

                if alt_url != db_url:
                    conn = try_connect(alt_url)
                    logging.info("Connected to Supabase using port 6543.")
                    return conn
            except Exception:
                pass

        logging.error(f"Database connection error: {e}")
        raise

def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        conn = connect_to_postgres(db_url)
        if conn:
            return PostgresConnectionWrapper(conn)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
