"""
services/bkt_engine.py — Simplified Bayesian Knowledge Tracing engine.

BKT parameters (p_learn, p_slip, p_guess) are loaded from the
system_settings table so they can be tuned per deployment without code
changes. Defaults are used when a live DB connection is not available
(e.g. in unit tests or cold-start before the pool is ready).

Parameter keys in system_settings:
    bkt_p_learn  — probability of learning on each attempt     (default 0.12)
    bkt_p_slip   — probability of slipping on a known concept  (default 0.10)
    bkt_p_guess  — probability of guessing correctly           (default 0.20)
"""

import threading

# ── In-memory cache: refresh at most once per 5 minutes ──────────────────────
_bkt_params_cache: dict = {}
_bkt_params_lock  = threading.Lock()
_bkt_params_ttl   = 0.0   # epoch seconds of last refresh

_BKT_DEFAULTS = {
    "bkt_p_learn": 0.12,
    "bkt_p_slip":  0.10,
    "bkt_p_guess": 0.20,
}


def _load_bkt_params(conn) -> dict:
    """Read BKT parameters from system_settings, caching for 5 minutes."""
    import time
    global _bkt_params_cache, _bkt_params_ttl

    now = time.monotonic()
    # Fast path: return cached values if still fresh
    if _bkt_params_cache and (now - _bkt_params_ttl) < 300:
        return _bkt_params_cache

    with _bkt_params_lock:
        # Re-check inside lock (another thread may have refreshed)
        if _bkt_params_cache and (now - time.monotonic()) < 300:
            return _bkt_params_cache
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT setting_key, setting_value
                FROM system_settings
                WHERE setting_key IN ('bkt_p_learn', 'bkt_p_slip', 'bkt_p_guess')
            """)
            rows = cur.fetchall()
            cur.close()
            params = dict(_BKT_DEFAULTS)
            for row in rows:
                try:
                    params[row["setting_key"]] = float(row["setting_value"])
                except (ValueError, TypeError):
                    pass
            _bkt_params_cache = params
            _bkt_params_ttl   = time.monotonic()
        except Exception:
            # DB unavailable — fall back to defaults silently
            _bkt_params_cache = dict(_BKT_DEFAULTS)
    return _bkt_params_cache


# ── Core BKT mathematics ──────────────────────────────────────────────────────

def update_bkt(p_mastery, correct, p_learn=0.12, p_slip=0.10, p_guess=0.20):
    """Single-observation BKT update.  Returns updated P(mastery)."""
    p_mastery = max(0.0, min(1.0, float(p_mastery)))
    if correct:
        numerator   = p_mastery * (1 - p_slip)
        denominator = numerator + (1 - p_mastery) * p_guess
    else:
        numerator   = p_mastery * p_slip
        denominator = numerator + (1 - p_mastery) * (1 - p_guess)
    posterior = numerator / denominator if denominator else p_mastery
    return round(posterior + (1 - posterior) * p_learn, 4)


def concept_confidence(score, attempts=1):
    base           = max(0, min(100, float(score))) / 100
    attempt_factor = min(1, attempts / 3)
    return round((base * 0.8 + attempt_factor * 0.2) * 100, 1)


# ── DB-backed update ──────────────────────────────────────────────────────────

def update_bkt_record(conn, learner_id, outcome_id, concept_tag, correct):
    """Fetch current BKT state from DB, apply one update, persist result.

    BKT parameters are read from system_settings (cached 5 min) so they
    can be adjusted by an admin without restarting the application.
    """
    params = _load_bkt_params(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id = %s AND outcome_id = %s AND concept_tag = %s
    """, (learner_id, outcome_id, concept_tag))
    row          = cur.fetchone()
    current      = row["probability_mastery"] if row else 0.20
    observations = row["observations"]        if row else 0

    updated = update_bkt(
        current,
        correct,
        p_learn=params["bkt_p_learn"],
        p_slip =params["bkt_p_slip"],
        p_guess=params["bkt_p_guess"],
    )

    cur.execute("""
        INSERT INTO bkt_mastery
            (learner_id, outcome_id, concept_tag, probability_mastery, observations)
        VALUES (%s, %s, %s, %s, 1)
        ON CONFLICT (learner_id, outcome_id, concept_tag)
        DO UPDATE SET
            probability_mastery = EXCLUDED.probability_mastery,
            observations        = bkt_mastery.observations + 1,
            updated_at          = NOW()
    """, (learner_id, outcome_id, concept_tag, updated))
    cur.close()
    return updated, observations + 1


def bkt_summary(conn, learner_id, outcome_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT concept_tag, probability_mastery, observations
        FROM bkt_mastery
        WHERE learner_id = %s AND outcome_id = %s
        ORDER BY concept_tag
    """, (learner_id, outcome_id))
    rows = cur.fetchall()
    cur.close()
    return rows
