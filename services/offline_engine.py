"""
services/offline_engine.py — Offline sync queue support (Supabase/PostgreSQL edition).

Queued events are stored in offline_sync_queue and synced when the learner reconnects.
"""
import json


def queue_offline_event(conn, learner_id, event_type, payload):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO offline_sync_queue (learner_id, event_type, payload, sync_status)
        VALUES (%s, %s, %s, 'Pending')
    """, (learner_id, event_type, json.dumps(payload)))
    cur.close()


def sync_summary(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT sync_status, COUNT(*) AS total
        FROM offline_sync_queue
        GROUP BY sync_status
    """)
    rows = cur.fetchall()
    cur.close()
    return {row["sync_status"]: row["total"] for row in rows}
