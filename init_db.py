"""
init_db.py — Initialise the Supabase/PostgreSQL database for Learn2Master.

Usage:
    python init_db.py

Reads database_v2_postgres.sql and executes it against the Supabase PostgreSQL
database defined in DATABASE_URL (.env).

IMPORTANT: The SQL file contains PostgreSQL dollar-quoted function bodies ($$).
Simple semicolon-splitting breaks on these, so this script executes the entire
file as one transaction using psycopg2's execute() with the full script text.

Re-running drops and recreates all tables (safe for development reset).
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit(
        "DATABASE_URL is not set.\n"
        "Create a .env file from .env.example and add your Supabase connection string."
    )

SQL_FILE = os.path.join(os.path.dirname(__file__), "database_v2_postgres.sql")

print(f"Reading schema from: {SQL_FILE}")
with open(SQL_FILE, "r", encoding="utf-8") as f:
    sql_script = f.read()

print("Connecting to Supabase PostgreSQL...")
conn = psycopg2.connect(DATABASE_URL)
# autocommit=True allows DDL (CREATE TABLE, etc.) and SET commands to run freely
conn.autocommit = True

try:
    with conn.cursor() as cur:
        print("Executing schema (this may take a few seconds)...")
        cur.execute(sql_script)
    print("\n✓ Learn2Master PostgreSQL schema created successfully!")
    print("✓ Tables, indexes, triggers, RLS policies and seed data are ready.")
    print("\nNext step:  python seed_data.py")
except psycopg2.Error as e:
    print(f"\n✗ Database error: {e}")
    print("\nTip: If you see 'already exists' errors, the schema is already installed.")
    print("     Run with a fresh Supabase project or DROP the tables first.")
    raise
finally:
    conn.close()
