"""
supabase_client.py — Supabase client singleton for Learn2Master.

Provides a single initialised supabase-py client reused across all requests.
Uses the SERVICE ROLE key so all backend operations bypass RLS — the Flask
application enforces access control via role_required decorators instead.

Usage:
    from supabase_client import get_supabase
    sb = get_supabase()
    sb.auth.sign_in_with_password(...)
    sb.storage.from_("bucket").upload(...)
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_supabase: Client | None = None


def get_supabase() -> Client:
    """Return the shared Supabase client, initialising on first call."""
    global _supabase
    if _supabase is not None:
        return _supabase

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url:
        raise RuntimeError(
            "SUPABASE_URL is not set. "
            "Add it to your .env file: SUPABASE_URL=https://<ref>.supabase.co"
        )
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is not set. "
            "Add it to your .env file — find it in Supabase → Settings → API → service_role."
        )

    _supabase = create_client(url, key)
    return _supabase
