# Implementation Plan: learn2master-real-implementation

## Overview

Implement five missing production capabilities for the Learn2Master Flask/PostgreSQL platform: teacher-driven content management, admin user provisioning, admin mastery threshold settings, offline-first assessment sync, and teacher-initiated proactive interventions. No seed data, no demo stubs — every task targets real database writes against the live Supabase/PostgreSQL schema.

## Tasks

- [x] 1. Register new blueprints in app.py
  - Import `content_bp` from `routes.content` and `sync_bp` from `routes.sync`
  - Call `app.register_blueprint(content_bp)` and `app.register_blueprint(sync_bp)` after existing registrations
  - Call `csrf.exempt(sync_bp)` immediately after registering `sync_bp` — the `/sync` JSON endpoint validates CSRF from the request body, not via Flask-WTF form middleware
  - **Requirement refs:** R1.17, R4.8

- [x] 2. Create routes/content.py — Learning Outcomes CRUD
  - Create `routes/content.py` with `content_bp = Blueprint("content", __name__)`
  - `GET /teacher/content/outcomes` — query `learning_outcomes` joined to `competencies` and `subjects`, ordered by `subject_name`, `sequence_order`; render `content/outcomes.html`
  - `POST /teacher/content/outcomes/create` — validate required fields, INSERT into `learning_outcomes`, commit, flash success, redirect
  - `GET /teacher/content/outcomes/<outcome_id>/edit` — fetch row, render edit form
  - `POST /teacher/content/outcomes/<outcome_id>/edit` — UPDATE `learning_outcomes`, commit, flash success, redirect
  - `POST /teacher/content/outcomes/<outcome_id>/delete` — check `SELECT mastery_id FROM mastery_records WHERE outcome_id = %s LIMIT 1`; if found flash danger and redirect without deleting; otherwise DELETE and commit
  - Apply `@role_required("teacher", "admin")` to all routes; use `get_db()` / `release_db()` via `try/finally`
  - **Requirement refs:** R1.1–R1.3, R1.17–R1.18

- [x] 3. Add Lessons CRUD to routes/content.py
  - `GET /teacher/content/lessons` — query `lessons` joined to `courses` and `learning_outcomes`; render `content/lessons.html`
  - `POST /teacher/content/lessons/create` — INSERT into `lessons` (`course_id`, `outcome_id`, `lesson_title`, `lesson_content`, `video_url`, `estimated_minutes`, `sequence_order`), commit, flash, redirect
  - `GET /teacher/content/lessons/<lesson_id>/edit` — fetch row, render edit form
  - `POST /teacher/content/lessons/<lesson_id>/edit` — UPDATE `lessons`, commit, flash, redirect
  - `POST /teacher/content/lessons/<lesson_id>/delete` — check `SELECT assessment_id FROM assessments WHERE lesson_id = %s LIMIT 1`; reject with flash if found; otherwise DELETE and commit
  - **Requirement refs:** R1.4–R1.6, R1.17–R1.18

- [x] 4. Add Questions CRUD (with options) to routes/content.py
  - `GET /teacher/content/questions` — query `questions` joined to `assessments` and `lessons`; render `content/questions.html`
  - `POST /teacher/content/questions/create` — parse `option_text` list via `request.form.getlist("option_text")` and `correct_option_index` (radio); validate 2–6 options and index in range; INSERT into `questions` then INSERT one row per option into `question_options` with `is_correct = TRUE` only on designated index; all inserts in single transaction; commit; flash; redirect
  - `GET /teacher/content/questions/<question_id>/edit` — fetch question + all options, render edit form
  - `POST /teacher/content/questions/<question_id>/edit` — UPDATE `questions` row; DELETE all existing `question_options` WHERE `question_id = %s`; INSERT fresh option set; all in single transaction; commit; flash; redirect
  - `POST /teacher/content/questions/<question_id>/delete` — DELETE `question_options` then `questions` in single transaction; commit; flash; redirect
  - **Requirement refs:** R1.7–R1.9, R1.17–R1.18

- [x] 5. Add Adaptive Notes CRUD to routes/content.py
  - `GET /teacher/content/notes` — query `adaptive_notes` joined to `learning_outcomes`; render `content/notes.html`
  - `POST /teacher/content/notes/create` — INSERT into `adaptive_notes` (`outcome_id`, `concept_tag`, `note_title`, `note_body`, `priority`); commit; flash; redirect
  - `GET /teacher/content/notes/<note_id>/edit` — fetch row, render edit form
  - `POST /teacher/content/notes/<note_id>/edit` — UPDATE row; commit; flash; redirect
  - `POST /teacher/content/notes/<note_id>/delete` — DELETE row; commit; flash; redirect
  - **Requirement refs:** R1.10–R1.12, R1.17–R1.18

- [x] 6. Add Adaptive Videos and Worked Examples CRUD to routes/content.py
  - `GET /teacher/content/videos` — query `adaptive_videos` joined to `learning_outcomes`; render `content/videos.html`
  - `POST /teacher/content/videos/create` — INSERT into `adaptive_videos` (`outcome_id`, `concept_tag`, `video_title`, `video_url`, `video_description`); commit; flash; redirect
  - `POST /teacher/content/videos/<video_id>/delete` — DELETE row; commit; flash; redirect
  - `GET /teacher/content/examples` — query `worked_examples` joined to `learning_outcomes`; render `content/examples.html`
  - `POST /teacher/content/examples/create` — INSERT into `worked_examples` (`outcome_id`, `concept_tag`, `example_title`, `example_body`, `step_by_step_solution`); commit; flash; redirect
  - `POST /teacher/content/examples/<example_id>/delete` — DELETE row; commit; flash; redirect
  - **Requirement refs:** R1.13–R1.16, R1.17–R1.18

- [x] 7. Add Admin Curriculum Routes to routes/content.py
  - `GET/POST /admin/content/subjects/create` — INSERT into `subjects`; `@role_required("admin")`
  - `GET/POST /admin/content/subjects/<subject_id>/edit` — UPDATE `subjects`; `@role_required("admin")`
  - `POST /admin/content/subjects/<subject_id>/delete` — DELETE `subjects`; `@role_required("admin")`
  - `/admin/content/competencies/...` routes — INSERT/UPDATE/DELETE against `competencies`; `@role_required("admin")`
  - `/admin/content/courses/...` routes — INSERT/UPDATE/DELETE against `courses`; `@role_required("admin")`
  - **Requirement refs:** R1.19–R1.20

- [x] 8. Create content management templates
  - `templates/content/outcomes.html` — list table (outcome_code, outcome_name, competency, mastery_threshold, sequence_order) + inline create form + Edit/Delete buttons per row; extend `layouts/base.html`; include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` on every form
  - `templates/content/lessons.html` — list table (lesson_title, course, outcome, estimated_minutes) + inline create form + Edit/Delete buttons
  - `templates/content/questions.html` — list table (question_text, concept_tag, difficulty_level, marks) + create form with dynamic option rows (JS: add/remove option inputs, radio for correct answer) + Delete button
  - `templates/content/notes.html` — list table (note_title, concept_tag, priority) + inline create form + Edit/Delete buttons
  - `templates/content/videos.html` — list table (video_title, concept_tag, video_url) + inline create form + Delete button
  - `templates/content/examples.html` — list table (example_title, concept_tag) + inline create form with textarea for `step_by_step_solution` + Delete button
  - **Requirement refs:** R1.1–R1.20

- [x] 9. Extend routes/admin.py — Admin User Management
  - Add `GET /admin/users/create` — query `schools` ordered by `school_name`; render `admin/create_user.html` with schools list; `@role_required("admin")`
  - Add `POST /admin/users/create` — validate `role in {"teacher", "admin"}` (`abort(400)` otherwise); `SELECT role_id FROM roles WHERE role_name = %s`; `generate_password_hash(password, method="pbkdf2:sha256")`; INSERT into `users`; catch `psycopg2.errors.UniqueViolation` → `conn.rollback()`, flash danger, redirect back to form; on success commit, flash, redirect to `admin.users`
  - Update `GET /admin/users` query to `ORDER BY role_name, full_name` and ensure `created_at` is selected
  - **Requirement refs:** R2.1–R2.7

- [x] 10. Create admin/create_user.html template and update admin/users.html
  - Create `templates/admin/create_user.html` — form with fields: `full_name`, `username`, `email`, `password`, `role` (select: teacher/admin), `school_id` (select from `schools`), hidden `csrf_token`, submit button; extend `layouts/base.html`
  - Add "Create User" link to `templates/admin/users.html` pointing to `url_for('admin.create_user')`
  - Add `created_at` column to the users table in `templates/admin/users.html`
  - **Requirement refs:** R2.1–R2.7

- [x] 11. Extend routes/admin.py — Admin Settings Management
  - Add `POST /admin/settings/threshold/<int:outcome_id>` — parse `mastery_threshold` from form; cast to `int`; validate `1 <= value <= 100` (flash danger + redirect on failure); `SELECT mastery_threshold FROM learning_outcomes WHERE outcome_id = %s` (`abort(404)` if not found); UPDATE `learning_outcomes SET mastery_threshold = %s`; INSERT into `audit_logs` with `actor_id = session["user_id"]`, `action = "update_mastery_threshold"`, `entity_type = "learning_outcomes"`, `entity_id = str(outcome_id)`, `details = json.dumps({"old": old_threshold, "new": new_threshold})`; commit; flash success; redirect to `admin.settings`
  - Apply `@role_required("admin")`
  - Update `GET /admin/settings` query to join `subjects` via `competencies`, select `subject_name` and `sequence_order`, order by `subject_name`, `sequence_order`; pass result as `thresholds` to template
  - **Requirement refs:** R3.1–R3.6

- [x] 12. Update templates/admin/settings.html for inline threshold editing
  - Replace read-only threshold pills with inline edit form per outcome row: `<form method="POST" action="{{ url_for('admin.update_threshold', outcome_id=t.outcome_id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="number" name="mastery_threshold" value="{{ t.mastery_threshold }}" min="1" max="100"><button type="submit">Save</button></form>`
  - Display `subject_name`, `outcome_code`, `outcome_name`, and current `mastery_threshold` per row
  - **Requirement refs:** R3.6

- [x] 13. Create routes/sync.py — Offline Assessment Sync Endpoint
  - Create `routes/sync.py` with `sync_bp = Blueprint("sync", __name__)`
  - `POST /sync` — auth guard: `if session.get("role") != "student": return jsonify({"error": "Forbidden"}), 403`
  - Parse JSON body: `body = request.get_json(force=True, silent=True) or {}`
  - CSRF validation: `validate_csrf(body.get("csrf_token"))` from `flask_wtf.csrf`; catch `ValidationError`; return HTTP 400 on failure
  - Extract `items = body.get("items") or [body]` to support single-item and batch payloads
  - Per-item loop: skip items where `int(item.get("learner_id", -1)) != session["user_id"]`; call `_process_sync_item(conn, learner_id, item)` inside `get_db()` / `release_db()` try/finally; on success commit + INSERT `offline_sync_queue` row with `sync_status = 'Synced'`, `synced_at = NOW()`; on exception rollback + INSERT `offline_sync_queue` row with `sync_status = 'Failed'` and error details; continue loop
  - Return `jsonify({"synced": synced}), 200`
  - **Requirement refs:** R4.3–R4.8

- [x] 14. Implement _process_sync_item in routes/sync.py
  - Read `assessment_id` from `item["_assessment_id"]`
  - Fetch assessment + lesson + outcome row (same SQL join as `learning.submit_assessment`)
  - Build answer map from `item` keys matching `question_<id>` pattern
  - Iterate questions, score answers, call `update_bkt_record(conn, learner_id, outcome_id, concept_tag, is_correct)`, build `concept_stats` dict
  - INSERT `assessment_attempts` row using `RETURNING attempt_id`; INSERT `attempt_answers` rows
  - Call `update_concept_mastery(conn, learner_id, outcome_id, assessment_type, concept_stats)` — import from `routes.learning`
  - Upsert `mastery_records` with updated pre/practice/post scores and `mastery_status` — identical ON CONFLICT logic as `routes/learning.submit_assessment`
  - INSERT `activity_logs` row with `activity_type = "Sync Submission Processed"` and description including `assessment_id` and `learner_id`
  - All operations use the passed `conn` — caller is responsible for commit or rollback
  - **Requirement refs:** R4.4–R4.5

- [x] 15. Update service-worker.js — Offline Assessment Interception
  - In the `fetch` event handler, add assessment interception branch **before** the existing static-asset cache branch: `const isAssessmentSubmit = event.request.method === 'POST' && /\/assessment\/\d+\/submit/.test(url.pathname)`
  - When `isAssessmentSubmit` is true: attempt `fetch(event.request.clone())`; on network failure clone the form body into a payload object, call `enqueueOffline(payload)`, return `new Response(JSON.stringify({ queued: true }), { status: 202, headers: { 'Content-Type': 'application/json' } })`
  - Implement `enqueueOffline(payload)` — opens `indexedDB.open('learn2master-offline', 1)` with `onupgradeneeded` creating `'offlineQueue'` store (autoIncrement keys); appends record `{ payload, status: 'pending', queued_at: timestamp }`
  - **Requirement refs:** R4.1, R4.9

- [x] 16. Update static/js/offline.js — Client-Side Sync on Reconnect
  - Append `window.addEventListener('online', syncOfflineQueue)` after existing service worker registration code
  - On page load, if `navigator.onLine`, call `syncOfflineQueue()` to replay items from previous offline sessions
  - Implement `syncOfflineQueue()` async function: open IndexedDB `'learn2master-offline'` / `'offlineQueue'`; retrieve all records; filter `status === 'pending'`; sort by key ascending (oldest first); for each pending record POST to `/sync` with `Content-Type: application/json` and body `{ ...value.payload, event_type: 'assessment_submission' }`; on HTTP 200 update IndexedDB record `status` to `'synced'`; on network error `break` and retry on next `online` event
  - Implement `openOfflineDB()` Promise wrapper around `indexedDB.open`
  - Implement `getAllRecords(store)` Promise wrapper returning `[{ key, value }]` from `IDBObjectStore.openCursor`
  - **Requirement refs:** R4.2, R4.7

- [x] 17. Extend routes/teacher.py — Learner Detail and Interventions
  - Add `GET /teacher/learners/<int:learner_id>` (`learner_detail`): validate learner exists with `role_name = 'student'` (`abort(404)` otherwise); query mastery summary (`learning_outcomes` LEFT JOIN `mastery_records`, joined to `competencies` and `subjects`, ordered by `subject_name`, `sequence_order`); query intervention history (`teacher_interventions` JOIN `learning_outcomes` WHERE `learner_id = %s` ORDER BY `created_at DESC`); query outcomes dropdown (`SELECT outcome_id, outcome_code, outcome_name FROM learning_outcomes ORDER BY outcome_code`); render `teacher/learner_detail.html`
  - Add `POST /teacher/learners/<int:learner_id>/intervene` (`intervene`): read and strip `intervention_type`, `intervention_note`, `target_outcome_id` from form; if either blank flash danger and redirect; validate learner is student (`abort(404)` if not); validate `outcome_id` exists (`abort(404)` if not); INSERT into `teacher_interventions` (`teacher_id`, `learner_id`, `outcome_id`, `intervention_type`, `intervention_note`, `status = 'Assigned'`); INSERT into `activity_logs` (`activity_type = 'Teacher Intervention Assigned'`, description with learner_id, outcome_id, intervention_type); commit; flash success; redirect to `teacher.learner_detail`
  - Apply `@role_required("teacher", "admin")` to both routes
  - **Requirement refs:** R5.1–R5.9

- [ ] 18. Create templates/teacher/learner_detail.html
  - Extend `layouts/base.html`
  - Section 1 — Learner header: `full_name`, `username`, `class_level`, `learning_style`, `learning_pace`
  - Section 2 — Mastery Summary table: columns Subject, Outcome Code, Outcome Name, Pretest, Practice, Posttest, Mastery Score, Status; rows from `mastery_rows`; colour-code Status (Mastered = green, In Progress = amber, Not Started = grey)
  - Section 3 — Assign Intervention form: POST to `url_for('teacher.intervene', learner_id=learner.user_id)`, fields: `target_outcome_id` (select from `outcomes`), `intervention_type` (select: Targeted Practice / One-to-One Session / Peer Support / Parent Contact / Referral), `intervention_note` (textarea), hidden `csrf_token`
  - Section 4 — Intervention History table: columns Outcome, Type, Note, Status, Date; rows from `interventions` ordered `created_at DESC`; empty-state message if no interventions
  - **Requirement refs:** R5.7–R5.8

- [x] 19. Write property-based tests — Content Management (Properties 1–5)
  - Create `tests/test_properties.py` using `pytest` and `hypothesis`
  - Property 1 (Insert Round-Trip): generate random valid outcome/note/video/example payloads; POST to create route; SELECT row; assert all submitted fields match DB row (validates R1.1, R1.4, R1.10, R1.13, R1.15)
  - Property 2 (Edit Reflects Updates): insert row; generate random field update; POST edit; SELECT; assert new values present and old changed values absent (validates R1.2, R1.5, R1.11)
  - Property 3 (Safe-Delete Referential Integrity): insert outcome + referencing `mastery_records` row; POST delete; assert outcome row still exists in DB (validates R1.3, R1.6)
  - Property 4 (Question Options Invariant): generate N options (2–6) and correct index; POST create; assert `COUNT(*) FROM question_options WHERE question_id = %s` == N; assert exactly one row has `is_correct = TRUE` (validates R1.7, R1.8)
  - Property 5 (Question Delete Cascade): insert question with K options; POST delete; assert question row gone and all K option rows gone (validates R1.9)

- [ ] 20. Write property-based tests — User Management and Settings (Properties 6–9)
  - Property 6 (Password Not Plaintext): generate random password; POST to `/admin/users/create`; SELECT `password_hash`; assert `password_hash != password`; assert `check_password_hash(stored, password) == True` (validates R2.1)
  - Property 7 (Duplicate User Leaves Table Unchanged): count `users` rows; POST with duplicate username or email; count again; assert counts equal (validates R2.2)
  - Property 8 (Student Registration Role Immutability): POST to `/register` with arbitrary role values in body; SELECT resulting row; assert `role_name == 'student'` (validates R2.6)
  - Property 9 (Threshold Audit Trail): POST valid threshold update; SELECT `learning_outcomes.mastery_threshold`; SELECT latest `audit_logs` row for that `outcome_id`; assert threshold matches; assert `details` JSON contains correct old/new values (validates R3.1, R3.6)

- [ ] 21. Write property-based tests — Sync and Interventions (Properties 10–14)
  - Property 10 (Sync Grading Equivalence): submit identical answer set via `/assessment/<id>/submit` on learner A and via `/sync` on learner B; assert `mastery_records` scores and `mastery_status` are equal for both learners (validates R4.4)
  - Property 11 (Sync Batch Resilience): build batch of N items with one malformed item at position K; POST to `/sync`; assert `offline_sync_queue` has N-1 `'Synced'` rows and exactly 1 `'Failed'` row for item K (validates R4.6)
  - Property 12 (Offline Queue Ordering): insert M IndexedDB records with distinct timestamps out of order; trigger `syncOfflineQueue()`; capture `/sync` request sequence; assert requests arrive in ascending timestamp order (validates R4.2)
  - Property 13 (Intervention Insert Completeness and Audit): POST valid intervention; SELECT `teacher_interventions` row; assert `teacher_id`, `learner_id`, `outcome_id`, `status = 'Assigned'` correct; SELECT `activity_logs`; assert row with `activity_type = 'Teacher Intervention Assigned'` exists (validates R5.1, R5.9)
  - Property 14 (Learner Detail Page Completeness): for learner with M mastery records and K interventions; GET `/teacher/learners/<id>`; assert HTML response contains all M mastery rows and all K intervention rows (validates R5.7, R5.8)

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [1] },
    { "wave": 2, "tasks": [2, 3, 4, 5, 6, 7, 9, 11, 13, 15, 17] },
    { "wave": 3, "tasks": [8, 10, 12, 14, 16, 18] },
    { "wave": 4, "tasks": [19, 20, 21] }
  ]
}
```

## Notes

- All DB writes use `get_db()` / `release_db()` inside `try/finally` blocks — no bare connections
- All HTML forms include `{{ csrf_token() }}` hidden input — Flask-WTF validates on every POST
- The `/sync` route is exempted from global CSRF middleware (`csrf.exempt(sync_bp)`) and validates the token from the JSON body using `validate_csrf()` directly
- No seed data is included in any task — teachers populate content through the management UI
- `_process_sync_item` must import `update_concept_mastery` and `update_bkt_record` from `routes.learning` to guarantee grading equivalence (Property 10)
- Password hashing uses `method="pbkdf2:sha256"` consistently with `routes/auth.py`
