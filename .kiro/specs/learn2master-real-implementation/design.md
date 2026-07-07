# Design Document

## Feature: learn2master-real-implementation

### Introduction

This document describes the architecture and implementation design for five production capabilities added to the Learn2Master Flask/PostgreSQL application. All design decisions conform to the existing codebase conventions: `get_db()` / `release_db()` pool pattern, `@role_required` guards, `%s` psycopg2 placeholders, Jinja2 POST/Redirect/GET forms with `{{ csrf_token() }}`, and `RealDictCursor` row access.

---

## Architecture Overview

The five capabilities map onto four file-level changes and two new files:

| Capability | Primary file(s) |
|---|---|
| Teacher Content Management | `routes/content.py` (new), `app.py` (blueprint register) |
| Admin User Management | `routes/admin.py` (extend) |
| Admin Settings Management | `routes/admin.py` (extend), `templates/admin/settings.html` (update) |
| Offline-First Assessment Sync | `static/js/offline.js` (update), `service-worker.js` (update), `routes/sync.py` (new), `app.py` (blueprint register) |
| Teacher Proactive Interventions | `routes/teacher.py` (extend), `templates/teacher/learner_detail.html` (new) |

All new templates extend `templates/layouts/base.html` and reside under their respective subdirectories (`templates/content/`, `templates/teacher/`).

---

## Component Design

### 1. Teacher Content Management — `routes/content.py`

#### Blueprint Registration

```python
# routes/content.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
import psycopg2
import psycopg2.errors
from routes.guards import role_required
from database import get_db, release_db

content_bp = Blueprint("content", __name__)
```

Registered in `app.py` alongside the existing blueprints:

```python
from routes.content import content_bp
from routes.sync import sync_bp
# ...
app.register_blueprint(content_bp)
app.register_blueprint(sync_bp)
```

#### URL Structure

| Role | Prefix | Resource |
|---|---|---|
| Teacher | `/teacher/content` | outcomes, lessons, questions, notes, videos, examples |
| Admin | `/admin/content` | subjects, competencies, courses |

#### Shared DB Write Pattern

Every write follows the borrow/commit/release pattern established in `routes/auth.py`:

```python
conn = get_db()
try:
    cur = conn.cursor()
    cur.execute("INSERT INTO ... VALUES (%s, %s, ...)", (val1, val2))
    conn.commit()
    cur.close()
finally:
    release_db(conn)
flash("Created successfully.", "success")
return redirect(url_for("content.list_outcomes"))
```

#### Safe-Delete Guard

Before any `DELETE` on outcomes or lessons, the route queries for referencing rows:

```python
# Outcome safe-delete
cur.execute(
    "SELECT mastery_id FROM mastery_records WHERE outcome_id = %s LIMIT 1",
    (outcome_id,)
)
if cur.fetchone():
    flash("Cannot delete: learners have mastery records for this outcome.", "danger")
    return redirect(url_for("content.list_outcomes"))

# Lesson safe-delete
cur.execute(
    "SELECT assessment_id FROM assessments WHERE lesson_id = %s LIMIT 1",
    (lesson_id,)
)
if cur.fetchone():
    flash("Cannot delete: assessments reference this lesson.", "danger")
    return redirect(url_for("content.list_lessons"))
```

Questions and their options are deleted in a single transaction (no external FK guard required — `question_options` FK is internal):

```python
cur.execute("DELETE FROM question_options WHERE question_id = %s", (question_id,))
cur.execute("DELETE FROM questions WHERE question_id = %s", (question_id,))
conn.commit()
```

#### Question Option Invariant

On question create and edit, exactly one `is_correct` flag must be `TRUE`. The form submits a single radio value (`correct_option_index`) identifying which option index is correct:

```python
option_texts = request.form.getlist("option_text")   # 2–6 values
correct_index = int(request.form.get("correct_option_index", -1))

if len(option_texts) < 2 or correct_index < 0 or correct_index >= len(option_texts):
    flash("A question requires at least 2 options and exactly one correct answer.", "danger")
    return redirect(...)
```

On edit, all existing options are deleted before inserting the new set within the same transaction, preserving atomicity.

#### Template Directory: `templates/content/`

| Template | Route |
|---|---|
| `outcomes.html` | `GET /teacher/content/outcomes` |
| `lessons.html` | `GET /teacher/content/lessons` |
| `questions.html` | `GET /teacher/content/questions` |
| `notes.html` | `GET /teacher/content/notes` |
| `videos.html` | `GET /teacher/content/videos` |
| `examples.html` | `GET /teacher/content/examples` |

Each template extends `layouts/base.html`, renders a list of existing items, and embeds an inline create form with `{{ csrf_token() }}` hidden input.

---

### 2. Admin User Management — `routes/admin.py` (extension)

#### New Route: `POST /admin/users/create`

```python
@admin_bp.route("/admin/users/create", methods=["GET", "POST"])
@role_required("admin")
def create_user():
    if request.method == "GET":
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT school_id, school_name FROM schools ORDER BY school_name")
            schools = cur.fetchall()
            cur.close()
        finally:
            release_db(conn)
        return render_template("admin/create_user.html", schools=schools)

    ALLOWED_ROLES = {"teacher", "admin"}
    full_name  = request.form.get("full_name", "").strip()
    username   = request.form.get("username", "").strip()
    email      = request.form.get("email", "").strip() or None
    password   = request.form.get("password", "")
    role       = request.form.get("role", "").strip()
    school_id  = request.form.get("school_id") or None

    if role not in ALLOWED_ROLES:
        abort(400)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM roles WHERE role_name = %s", (role,))
        role_row = cur.fetchone()
        if not role_row:
            abort(400)

        from werkzeug.security import generate_password_hash
        cur.execute("""
            INSERT INTO users (full_name, username, email, password_hash, role_id, school_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            full_name, username, email,
            generate_password_hash(password, method="pbkdf2:sha256"),
            role_row["role_id"], school_id
        ))
        conn.commit()
        cur.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash("Username or email already exists.", "danger")
        return redirect(url_for("admin.create_user"))
    finally:
        release_db(conn)

    flash(f"{role.title()} account created successfully.", "success")
    return redirect(url_for("admin.users"))
```

The existing `GET /admin/users` query already returns `role_name` and `school_name`; only the template `templates/admin/users.html` requires a `created_at` column addition for display (the query already selects it).


---

### 3. Admin Settings Management — `routes/admin.py` (extension)

#### New Route: `POST /admin/settings/threshold/<outcome_id>`

```python
@admin_bp.route("/admin/settings/threshold/<int:outcome_id>", methods=["POST"])
@role_required("admin")
def update_threshold(outcome_id):
    raw = request.form.get("mastery_threshold", "")
    try:
        new_threshold = int(raw)
        if not (1 <= new_threshold <= 100):
            raise ValueError
    except (ValueError, TypeError):
        flash("Threshold must be an integer between 1 and 100.", "danger")
        return redirect(url_for("admin.settings"))

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT mastery_threshold FROM learning_outcomes WHERE outcome_id = %s",
            (outcome_id,)
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            abort(404)

        old_threshold = row["mastery_threshold"]
        cur.execute(
            "UPDATE learning_outcomes SET mastery_threshold = %s WHERE outcome_id = %s",
            (new_threshold, outcome_id)
        )
        import json
        cur.execute("""
            INSERT INTO audit_logs
                (actor_id, action, entity_type, entity_id, details)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            session["user_id"],
            "update_mastery_threshold",
            "learning_outcomes",
            str(outcome_id),
            json.dumps({"old": old_threshold, "new": new_threshold})
        ))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash(f"Threshold updated to {new_threshold}%.", "success")
    return redirect(url_for("admin.settings"))
```

#### Template Update: `templates/admin/settings.html`

The existing template renders outcome thresholds as read-only pills. The updated template replaces each pill with an inline form row:

```html
{% for t in thresholds %}
<div class="concept-pill">
  <span>{{ t.subject_name }} • {{ t.outcome_code }}</span>
  <small>{{ t.outcome_name }}</small>
  <form method="POST"
        action="{{ url_for('admin.update_threshold', outcome_id=t.outcome_id) }}"
        style="display:inline">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="number" name="mastery_threshold"
           value="{{ t.mastery_threshold }}" min="1" max="100"
           style="width:5rem">
    <button type="submit" class="btn-sm">Save</button>
  </form>
</div>
{% endfor %}
```

---

### 4. Offline-First Assessment Sync

This capability has three coordinated layers: browser IndexedDB queue, service worker interception, and Flask sync endpoint.

#### 4a. Service Worker Update — `service-worker.js`

The fetch handler gains a new branch that intercepts `POST /assessment/*/submit` while offline:

```javascript
// In the 'fetch' event handler, before the existing static-asset branch:
const isAssessmentSubmit =
  event.request.method === 'POST' &&
  /\/assessment\/\d+\/submit/.test(url.pathname);

if (isAssessmentSubmit) {
  event.respondWith(
    fetch(event.request.clone()).catch(async () => {
      // Offline path: clone body, store in IndexedDB, return synthetic response
      const formData = await event.request.formData();
      const payload  = {};
      for (const [key, val] of formData.entries()) payload[key] = val;
      payload._assessment_id = url.pathname.split('/')[2];
      payload._queued_at     = Date.now();
      await enqueueOffline(payload);
      return new Response(
        JSON.stringify({ queued: true }),
        { status: 202, headers: { 'Content-Type': 'application/json' } }
      );
    })
  );
  return;
}
```

The `enqueueOffline(payload)` helper opens the `'offlineQueue'` IndexedDB object store and appends a record `{ payload, status: 'pending', queued_at: timestamp }`. The store uses an auto-increment key.

```javascript
function enqueueOffline(payload) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('learn2master-offline', 1);
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore('offlineQueue', { autoIncrement: true });
    };
    req.onsuccess = e => {
      const db    = e.target.result;
      const tx    = db.transaction('offlineQueue', 'readwrite');
      const store = tx.objectStore('offlineQueue');
      store.add({ payload, status: 'pending', queued_at: payload._queued_at });
      tx.oncomplete = resolve;
      tx.onerror    = reject;
    };
    req.onerror = reject;
  });
}
```

#### 4b. Client-Side Sync — `static/js/offline.js`

The existing file registers the service worker. Sync logic is appended:

```javascript
// Listen for connectivity restoration
window.addEventListener('online', syncOfflineQueue);

async function syncOfflineQueue() {
  const db = await openOfflineDB();
  const tx = db.transaction('offlineQueue', 'readwrite');
  const store = tx.objectStore('offlineQueue');

  // Collect all pending records ordered by key (oldest first, autoIncrement)
  const all = await getAllRecords(store);
  const pending = all.filter(r => r.value.status === 'pending')
                     .sort((a, b) => a.key - b.key);

  for (const { key, value } of pending) {
    const body = { ...value.payload, event_type: 'assessment_submission' };
    try {
      const resp = await fetch('/sync', {
        method: 'POST',
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' }
      });
      if (resp.ok) {
        // Mark as synced — update the record in-place
        const upTx    = db.transaction('offlineQueue', 'readwrite');
        const upStore = upTx.objectStore('offlineQueue');
        upStore.put({ ...value, status: 'synced' }, key);
        await new Promise(r => upTx.oncomplete = r);
      }
    } catch (_) {
      // Network failure mid-sync — stop and retry on next 'online' event
      break;
    }
  }
}
```

`openOfflineDB()` and `getAllRecords()` are small Promise-based wrappers around `indexedDB.open` and `IDBObjectStore.getAll`.


#### 4c. Flask Sync Endpoint — `routes/sync.py`

```python
"""routes/sync.py — Offline assessment sync endpoint."""
import json
from collections import defaultdict
from flask import Blueprint, request, jsonify, session
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from database import get_db, release_db
from routes.learning import (
    get_required_concepts, posttest_unlock_status, update_concept_mastery,
    update_bkt_record,
)
from services.mastery_engine import (
    calculate_percentage, mastery_level, evidence_based_mastery,
)
from services.offline_engine import queue_offline_event

sync_bp = Blueprint("sync", __name__)


@sync_bp.route("/sync", methods=["POST"])
def sync():
    # ── Auth guard ─────────────────────────────────────────────────
    if session.get("role") != "student":
        return jsonify({"error": "Forbidden"}), 403

    learner_id = session["user_id"]

    # ── CSRF: validate from JSON body ──────────────────────────────
    body = request.get_json(force=True, silent=True) or {}
    try:
        validate_csrf(body.get("csrf_token"))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    items = body.get("items") or [body]  # single-item or batch
    synced = 0

    for item in items:
        if int(item.get("learner_id", -1)) != learner_id:
            # Payload learner_id mismatch — skip silently (403 was checked above)
            continue

        conn = get_db()
        try:
            _process_sync_item(conn, learner_id, item)
            conn.commit()
            # Record as Synced
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO offline_sync_queue
                    (learner_id, event_type, payload, sync_status, synced_at)
                VALUES (%s, %s, %s, 'Synced', NOW())
            """, (learner_id, item.get("event_type", "assessment_submission"),
                  json.dumps(item)))
            conn.commit()
            cur.close()
            synced += 1
        except Exception as exc:
            conn.rollback()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO offline_sync_queue
                        (learner_id, event_type, payload, sync_status)
                    VALUES (%s, %s, %s, 'Failed')
                """, (learner_id, item.get("event_type", "unknown"),
                      json.dumps({"error": str(exc), "item": item})))
                conn.commit()
                cur.close()
            except Exception:
                conn.rollback()
        finally:
            release_db(conn)

    return jsonify({"synced": synced}), 200
```

`_process_sync_item()` replicates the grading logic from `routes/learning.submit_assessment`, but reads the answer map from the JSON payload (`question_<id>` keys) rather than `request.form`. It calls `update_concept_mastery()`, `update_bkt_record()`, upserts `mastery_records`, and inserts `activity_logs` — identical to the live submission path, satisfying the model-based equivalence property.

The `/sync` route is **exempt from the standard WTF CSRF form validation** because it is a JSON endpoint. Instead it reads and validates `csrf_token` from the JSON body using `flask_wtf.csrf.validate_csrf()`. To exempt the route from the global CSRF protection, `csrf.exempt(sync_bp)` is called after blueprint registration in `app.py`.

---

### 5. Teacher Proactive Interventions — `routes/teacher.py` (extension)

#### New Route: `POST /teacher/learners/<learner_id>/intervene`

```python
@teacher_bp.route("/teacher/learners/<int:learner_id>/intervene", methods=["POST"])
@role_required("teacher", "admin")
def intervene(learner_id):
    intervention_type = (request.form.get("intervention_type") or "").strip()
    intervention_note = (request.form.get("intervention_note") or "").strip()
    target_outcome_id = request.form.get("target_outcome_id")

    if not intervention_type or not intervention_note:
        flash("Intervention type and note are required.", "danger")
        return redirect(url_for("teacher.learner_detail", learner_id=learner_id))

    conn = get_db()
    try:
        cur = conn.cursor()

        # Validate learner is a student
        cur.execute("""
            SELECT users.user_id FROM users
            JOIN roles ON users.role_id = roles.role_id
            WHERE users.user_id = %s AND roles.role_name = 'student'
        """, (learner_id,))
        if not cur.fetchone():
            cur.close()
            abort(404)

        # Validate outcome exists
        cur.execute(
            "SELECT outcome_id FROM learning_outcomes WHERE outcome_id = %s",
            (target_outcome_id,)
        )
        if not cur.fetchone():
            cur.close()
            abort(404)

        cur.execute("""
            INSERT INTO teacher_interventions
                (teacher_id, learner_id, outcome_id,
                 intervention_type, intervention_note, status)
            VALUES (%s, %s, %s, %s, %s, 'Assigned')
        """, (session["user_id"], learner_id, target_outcome_id,
              intervention_type, intervention_note))

        cur.execute("""
            INSERT INTO activity_logs
                (learner_id, activity_type, activity_description)
            VALUES (%s, %s, %s)
        """, (
            learner_id,
            "Teacher Intervention Assigned",
            f"Outcome {target_outcome_id}: {intervention_type} by teacher {session['user_id']}."
        ))
        conn.commit()
        cur.close()
    finally:
        release_db(conn)

    flash("Intervention assigned successfully.", "success")
    return redirect(url_for("teacher.learner_detail", learner_id=learner_id))
```

#### New Route: `GET /teacher/learners/<learner_id>`

```python
@teacher_bp.route("/teacher/learners/<int:learner_id>")
@role_required("teacher", "admin")
def learner_detail(learner_id):
    conn = get_db()
    try:
        cur = conn.cursor()

        # Validate learner is a student
        cur.execute("""
            SELECT users.*, lp.class_level, lp.learning_style, lp.learning_pace
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            LEFT JOIN learner_profiles lp ON lp.learner_id = users.user_id
            WHERE users.user_id = %s AND roles.role_name = 'student'
        """, (learner_id,))
        learner = cur.fetchone()
        if not learner:
            abort(404)

        # Mastery summary
        cur.execute("""
            SELECT lo.outcome_name, lo.outcome_code, s.subject_name,
                   COALESCE(mr.pretest_score,  0) AS pretest_score,
                   COALESCE(mr.practice_score, 0) AS practice_score,
                   COALESCE(mr.posttest_score, 0) AS posttest_score,
                   COALESCE(mr.mastery_score,  0) AS mastery_score,
                   COALESCE(mr.mastery_status, 'Not Started') AS mastery_status
            FROM learning_outcomes lo
            JOIN competencies c ON lo.competency_id = c.competency_id
            JOIN subjects s ON c.subject_id = s.subject_id
            LEFT JOIN mastery_records mr
                ON mr.outcome_id = lo.outcome_id AND mr.learner_id = %s
            ORDER BY s.subject_name, lo.sequence_order
        """, (learner_id,))
        mastery_rows = cur.fetchall()

        # Intervention history
        cur.execute("""
            SELECT ti.intervention_type, ti.intervention_note,
                   ti.status, ti.created_at,
                   lo.outcome_name
            FROM teacher_interventions ti
            JOIN learning_outcomes lo ON ti.outcome_id = lo.outcome_id
            WHERE ti.learner_id = %s
            ORDER BY ti.created_at DESC
        """, (learner_id,))
        interventions = cur.fetchall()

        # Outcomes list for the intervention form dropdown
        cur.execute("""
            SELECT outcome_id, outcome_code, outcome_name FROM learning_outcomes
            ORDER BY outcome_code
        """)
        outcomes = cur.fetchall()
        cur.close()
    finally:
        release_db(conn)

    return render_template(
        "teacher/learner_detail.html",
        learner=learner,
        mastery_rows=mastery_rows,
        interventions=interventions,
        outcomes=outcomes,
    )
```

#### Template: `templates/teacher/learner_detail.html`

The template extends `layouts/base.html` and renders three sections:

1. **Mastery Summary** — a table with columns: Subject, Outcome, Pretest, Practice, Posttest, Mastery Score, Status.
2. **Intervention Form** — `POST` to `teacher.intervene`, fields: `target_outcome_id` (select), `intervention_type` (select: Targeted Practice / One-to-One Session / Peer Support / Parent Contact / Referral), `intervention_note` (textarea), hidden `csrf_token`.
3. **Intervention History** — a table ordered by `created_at DESC`: Outcome, Type, Note, Status, Date.

---

## Data Models

No schema changes are required. All tables used by these five capabilities are already defined in `database_v2_postgres.sql`:

| Table | Used by |
|---|---|
| `learning_outcomes` | Content management (R1), Settings (R3) |
| `lessons` | Content management (R1) |
| `questions`, `question_options` | Content management (R1) |
| `adaptive_notes`, `adaptive_videos`, `worked_examples` | Content management (R1) |
| `subjects`, `competencies`, `courses` | Content management admin routes (R1) |
| `users`, `roles`, `schools` | User management (R2) |
| `audit_logs` | Settings management (R3) |
| `offline_sync_queue` | Sync (R4) |
| `mastery_records`, `concept_mastery`, `bkt_mastery` | Sync grading (R4) |
| `assessment_attempts`, `attempt_answers` | Sync grading (R4) |
| `activity_logs` | Sync (R4), Interventions (R5) |
| `teacher_interventions` | Interventions (R5) |


---

## Error Handling

| Scenario | Handling |
|---|---|
| Safe-delete FK violation | Flash error, redirect — no DB change |
| `psycopg2.errors.UniqueViolation` on user create | `rollback()`, flash error, redirect to form |
| Invalid/out-of-range threshold | Integer cast + range check, flash error, no DB write |
| Non-existent `outcome_id` in threshold update | `abort(404)` |
| Non-existent or non-student `learner_id` in intervention | `abort(404)` |
| Invalid role in user create | `abort(400)` |
| Missing CSRF token on any form | Flask-WTF returns HTTP 400 automatically |
| Invalid CSRF token in `/sync` JSON body | `validate_csrf()` raises `ValidationError`; route returns HTTP 400 |
| Sync item processing exception | Per-item `rollback()`, `'Failed'` row written, batch continues |
| ServiceWorker offline and non-static route | `fetch()` rejects; application code should handle `202 Queued` response for assessment submits and show a UI banner |

---

## Security Design

- All teacher content routes protected by `@role_required("teacher", "admin")`.
- All admin routes protected by `@role_required("admin")`.
- Role whitelist in user create (`{"teacher", "admin"}`) prevents privilege escalation; the existing `routes/auth.register` hardcodes `"student"` independently.
- `/sync` performs server-side `learner_id` validation: payload `learner_id` must equal `session['user_id']`. A student cannot replay another learner's submissions.
- Password hashing: `generate_password_hash(password, method="pbkdf2:sha256")` — consistent with `routes/auth.py`.
- CSRF tokens present on all HTML forms and validated via Flask-WTF. The `/sync` JSON endpoint uses `validate_csrf()` from the JSON body.
- The service worker only stores form field values in IndexedDB (client-side). No secrets or session tokens are stored; the CSRF token stored in the queue is the one issued for that session and is validated server-side on replay.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Content Item Insert Round-Trip

*For any* valid content item (learning outcome, lesson, adaptive note, adaptive video, or worked example) submitted to the corresponding create route, the item should be immediately retrievable from the database with all submitted fields intact.

**Validates: Requirements 1.1, 1.4, 1.10, 1.13, 1.15**

### Property 2: Content Item Edit Reflects Updated Fields

*For any* existing content item row and any non-empty updated field set, submitting an edit should result in the database row containing the new field values and none of the old values that were changed.

**Validates: Requirements 1.2, 1.5, 1.11**

### Property 3: Safe-Delete Referential Integrity

*For any* learning outcome (or lesson), if at least one row in `mastery_records` (or `assessments`) references that item's ID, then a delete request for that item should leave the item row present in the database and the referencing rows intact.

**Validates: Requirements 1.3, 1.6**

### Property 4: Question Options Invariant

*For any* question create or edit submission with N options (2 ≤ N ≤ 6) and exactly one designated correct option, the `question_options` table should contain exactly N rows for that `question_id`, with `is_correct = TRUE` on exactly the designated option and `is_correct = FALSE` on all others.

**Validates: Requirements 1.7, 1.8**

### Property 5: Question Delete Cascade

*For any* question row with K associated `question_options` rows, after the delete request, neither the question row nor any of its K option rows should be present in the database.

**Validates: Requirement 1.9**

### Property 6: User Creation Password Never Stored in Plaintext

*For any* admin user-creation submission with a given password string, the `password_hash` stored in the `users` table should not equal the original password string, and `werkzeug.security.check_password_hash(stored_hash, original)` should return `True`.

**Validates: Requirement 2.1**

### Property 7: Duplicate Username/Email Leaves User Table Unchanged

*For any* username or email value that already exists in `users`, a create-user POST with that same username or email should result in the `users` table having the same row count as before the request.

**Validates: Requirement 2.2**

### Property 8: Student Registration Role Immutability

*For any* POST to `/register` containing any value for a role field in the request body (including `'teacher'`, `'admin'`, or arbitrary strings), the resulting `users` row must have `role_name = 'student'`.

**Validates: Requirement 2.6**

### Property 9: Threshold Update Audit Trail

*For any* valid mastery threshold update to an existing `outcome_id`, both the `learning_outcomes.mastery_threshold` column and a corresponding `audit_logs` row must reflect the change: the outcome row must contain the new threshold value, and the audit log row must record the old threshold and new threshold in its `details` JSON field.

**Validates: Requirements 3.1, 3.6**

### Property 10: Sync Grading Equivalence

*For any* valid assessment answer set, the `mastery_records`, `concept_mastery`, and `bkt_mastery` state produced by processing the submission via `POST /sync` should be equivalent to the state that would be produced by processing the same submission via `POST /assessment/<id>/submit` directly.

**Validates: Requirement 4.4**

### Property 11: Sync Batch Resilience

*For any* batch of N sync items where item K contains a malformed payload that causes a processing exception, items 1..K-1 and K+1..N should each produce a `'Synced'` row in `offline_sync_queue`, item K should produce a `'Failed'` row, and no partial DB writes from item K should be committed.

**Validates: Requirement 4.6**

### Property 12: Offline Queue Ordering

*For any* set of queued IndexedDB records with distinct `queued_at` timestamps, the sync replay should submit them to `/sync` in ascending timestamp order (oldest first), such that the sequence of HTTP requests matches the chronological order of original submissions.

**Validates: Requirement 4.2**

### Property 13: Intervention Insert Completeness and Audit

*For any* valid intervention submission by a teacher for a student learner and existing outcome, the resulting `teacher_interventions` row must have `teacher_id = session['user_id']`, `learner_id` matching the URL parameter, `outcome_id = target_outcome_id`, and `status = 'Assigned'`; and an `activity_logs` row with `activity_type = 'Teacher Intervention Assigned'` must exist referencing the same `learner_id` and `outcome_id`.

**Validates: Requirements 5.1, 5.9**

### Property 14: Learner Detail Page Completeness

*For any* learner with M mastery records and K intervention records, the `GET /teacher/learners/<learner_id>` response should include all M mastery rows (each with `pretest_score`, `practice_score`, `posttest_score`, `mastery_score`, `mastery_status`) and all K intervention rows (each with `outcome_name`, `intervention_type`, `intervention_note`, `status`, `created_at`), ordered by `created_at DESC` for interventions.

**Validates: Requirements 5.7, 5.8**

---

## Testing Strategy

### Unit / Example-Based Tests

- Access control: verify student/unauthenticated sessions are redirected from teacher and admin routes.
- CSRF: verify HTTP 400 on missing or invalid CSRF token for every protected POST route.
- Role whitelist: verify `abort(400)` when `role='student'` or arbitrary string is submitted to `/admin/users/create`.
- Non-existent IDs: verify HTTP 404 for `outcome_id` / `learner_id` that don't exist.
- Threshold boundary: verify rejection for values `0`, `101`, `-1`, and `'abc'`.

### Property-Based Tests

Each property above (1–14) is implemented as a property-based test using a PBT library (e.g., Hypothesis for Python, fast-check for JavaScript). Generators produce randomised content item data, user credentials, answer sets, threshold values, and intervention payloads. Each test runs a minimum of 100 iterations.

Test tag format: `Feature: learn2master-real-implementation, Property {N}: {title}`

The dual approach ensures specific known edge cases (CSRF, role validation, boundary values) are covered by deterministic unit tests, while universal invariants (insert correctness, cascade deletes, sync equivalence, audit trails) are validated across the full input space by property tests.
