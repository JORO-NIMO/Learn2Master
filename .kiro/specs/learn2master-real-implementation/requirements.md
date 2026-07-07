# Requirements Document

## Introduction

This document specifies five missing production capabilities for the Learn2Master adaptive learning platform built on Flask and PostgreSQL (Supabase). All five features target real data management and real user workflows: teacher-driven content authoring, administrator account provisioning, administrator mastery threshold configuration, offline-first assessment submission with background sync, and teacher-initiated proactive learner interventions. No seed data, demo stubs, or placeholder logic is in scope. Every route, database write, and client-side behaviour described here must function against the live PostgreSQL schema defined in `database_v2_postgres.sql`.

## Glossary

- **System**: The Learn2Master Flask/PostgreSQL web application.
- **Teacher**: An authenticated user whose `roles.role_name` is `'teacher'`.
- **Admin**: An authenticated user whose `roles.role_name` is `'admin'`.
- **Student**: An authenticated user whose `roles.role_name` is `'student'`.
- **ContentItem**: Any one of: learning outcome, lesson, question (with options), adaptive note, adaptive video, or worked example stored in the PostgreSQL schema.
- **Subject**: A row in the `subjects` table.
- **Competency**: A row in the `competencies` table linked to a Subject.
- **Course**: A row in the `courses` table linked to a Subject.
- **LearningOutcome**: A row in the `learning_outcomes` table linked to a Competency.
- **Lesson**: A row in the `lessons` table linked to a Course and a LearningOutcome.
- **Question**: A row in the `questions` table linked to an Assessment, with one or more rows in `question_options`; exactly one option has `is_correct = TRUE`.
- **AdaptiveNote**: A row in the `adaptive_notes` table linked to a LearningOutcome.
- **AdaptiveVideo**: A row in the `adaptive_videos` table linked to a LearningOutcome.
- **WorkedExample**: A row in the `worked_examples` table linked to a LearningOutcome.
- **MasteryThreshold**: The integer column `learning_outcomes.mastery_threshold` (default 80), used by `mastery_engine.mastery_status()` to classify a learner as "Mastered".
- **SyncQueue**: The `offline_sync_queue` table that stores pending assessment submission payloads with `sync_status = 'Pending'`.
- **ServiceWorker**: The `service-worker.js` file registered via `static/js/offline.js` in the learner's browser.
- **IndexedDB**: The browser-native key-value store used by the ServiceWorker to persist queued assessment submissions while the device is offline.
- **SyncEndpoint**: The Flask route `POST /sync` that processes records from the SyncQueue.
- **Intervention**: A row in the `teacher_interventions` table recording a Teacher's direct action for a specific learner and LearningOutcome.
- **get_db_connection**: The application function `database.get_db()` combined with `database.release_db()`, used by all Flask routes to borrow and return a pooled psycopg2 connection.
- **CSRF Token**: The Flask-WTF hidden field `{{ form.hidden_tag() }}` or `{{ csrf_token() }}` that must be present on every HTML form POST.
- **role_required**: The decorator defined in `routes/guards.py` that reads `session['role']` and rejects requests from unauthorised roles.
- **BKT Engine**: `services/bkt_engine.py` implementing Bayesian Knowledge Tracing, called during assessment submission to update `bkt_mastery` per concept.
- **MasteryEngine**: `services/mastery_engine.py` that calculates `mastery_score`, `mastery_level`, and `mastery_status` from pre-test, practice, and post-test scores.

---

## Requirements

### Requirement 1: Teacher Content Management

**User Story:** As a Teacher, I want to create, edit, and delete learning outcomes, lessons, questions (MCQ with options), adaptive notes, adaptive videos, and worked examples for subjects I teach, so that learners have accurate, up-to-date content without requiring admin involvement for every change.

#### Acceptance Criteria

1. WHEN a Teacher submits a valid POST request to `/teacher/content/outcomes/create` with `competency_id`, `outcome_code`, `outcome_name`, `outcome_description`, `mastery_threshold`, and `sequence_order`, THE System SHALL insert a new row into `learning_outcomes` and redirect to the outcome list page with a success flash message.

2. WHEN a Teacher submits a valid POST request to `/teacher/content/outcomes/<outcome_id>/edit` with one or more changed fields, THE System SHALL update the corresponding `learning_outcomes` row in PostgreSQL and redirect back with a success flash message.

3. WHEN a Teacher submits a POST request to `/teacher/content/outcomes/<outcome_id>/delete`, THE System SHALL delete the `learning_outcomes` row only if no `mastery_records` rows reference that `outcome_id`; IF referencing mastery records exist, THEN THE System SHALL reject the deletion and return an error flash message without modifying the database.

4. WHEN a Teacher submits a valid POST request to `/teacher/content/lessons/create` with `course_id`, `outcome_id`, `lesson_title`, `lesson_content`, `video_url`, `estimated_minutes`, and `sequence_order`, THE System SHALL insert a new row into `lessons` and redirect with a success flash message.

5. WHEN a Teacher submits a valid POST request to `/teacher/content/lessons/<lesson_id>/edit`, THE System SHALL update the `lessons` row and redirect with a success flash message.

6. WHEN a Teacher submits a POST request to `/teacher/content/lessons/<lesson_id>/delete`, THE System SHALL delete the `lessons` row only if no `assessments` rows reference that `lesson_id`; IF referencing assessments exist, THEN THE System SHALL reject the deletion and return an error flash message.

7. WHEN a Teacher submits a valid POST request to `/teacher/content/questions/create` with `assessment_id`, `question_text`, `concept_tag`, `difficulty_level`, `marks`, a list of `option_text` values (minimum 2, maximum 6), and exactly one `is_correct` flag, THE System SHALL insert one row into `questions` and one row per option into `question_options`, with `is_correct = TRUE` on the designated option, then redirect with a success flash message.

8. WHEN a Teacher submits a valid POST request to `/teacher/content/questions/<question_id>/edit` including updated option data, THE System SHALL update the `questions` row and replace all existing `question_options` rows for that `question_id` with the new option set in a single database transaction.

9. WHEN a Teacher submits a POST request to `/teacher/content/questions/<question_id>/delete`, THE System SHALL delete the `questions` row and all associated `question_options` rows in a single database transaction.

10. WHEN a Teacher submits a valid POST request to `/teacher/content/notes/create` with `outcome_id`, `concept_tag`, `note_title`, `note_body`, and `priority`, THE System SHALL insert a new row into `adaptive_notes` and redirect with a success flash message.

11. WHEN a Teacher submits a valid POST request to `/teacher/content/notes/<note_id>/edit`, THE System SHALL update the `adaptive_notes` row and redirect with a success flash message.

12. WHEN a Teacher submits a POST request to `/teacher/content/notes/<note_id>/delete`, THE System SHALL delete the `adaptive_notes` row and redirect with a success flash message.

13. WHEN a Teacher submits a valid POST request to `/teacher/content/videos/create` with `outcome_id`, `concept_tag`, `video_title`, `video_url`, and `video_description`, THE System SHALL insert a new row into `adaptive_videos` and redirect with a success flash message.

14. WHEN a Teacher submits a POST request to `/teacher/content/videos/<video_id>/delete`, THE System SHALL delete the `adaptive_videos` row and redirect with a success flash message.

15. WHEN a Teacher submits a valid POST request to `/teacher/content/examples/create` with `outcome_id`, `concept_tag`, `example_title`, `example_body`, and `step_by_step_solution`, THE System SHALL insert a new row into `worked_examples` and redirect with a success flash message.

16. WHEN a Teacher submits a POST request to `/teacher/content/examples/<example_id>/delete`, THE System SHALL delete the `worked_examples` row and redirect with a success flash message.

17. THE System SHALL protect all content-management routes with the `role_required("teacher", "admin")` decorator so that unauthenticated requests and requests from Student-role sessions are rejected with a redirect to the dashboard.

18. THE System SHALL include a valid CSRF token on every content-management HTML form and validate it on every POST request; IF the CSRF token is absent or invalid, THEN THE System SHALL return HTTP 400 without modifying the database.

19. WHEN an Admin accesses `/admin/content/subjects/create`, `/admin/content/subjects/<subject_id>/edit`, or `/admin/content/subjects/<subject_id>/delete`, THE System SHALL apply the same insert/update/delete pattern against the `subjects` table, protected by `role_required("admin")`.

20. WHEN an Admin accesses the competency and course management routes under `/admin/content/`, THE System SHALL apply insert/update/delete operations against the `competencies` and `courses` tables respectively, protected by `role_required("admin")`.

---

### Requirement 2: Admin User Management

**User Story:** As an Admin, I want to create teacher and admin accounts directly from the admin panel without exposing the registration form to those roles, so that only students can self-register and privileged accounts are provisioned in a controlled manner.

#### Acceptance Criteria

1. WHEN an Admin submits a valid POST request to `/admin/users/create` with `full_name`, `username`, `email`, `password`, `role` (one of `'teacher'` or `'admin'`), and `school_id`, THE System SHALL hash the password using `werkzeug.security.generate_password_hash`, insert a new row into `users` with the resolved `role_id`, and redirect to `/admin/users` with a success flash message.

2. WHEN an Admin submits a POST request to `/admin/users/create` with a `username` or `email` value that already exists in `users`, THE System SHALL roll back the transaction, return the user creation form with an error flash message, and leave the `users` table unchanged.

3. WHEN an Admin submits a POST request to `/admin/users/create` with a `role` value other than `'teacher'` or `'admin'`, THE System SHALL reject the request with HTTP 400 and leave the `users` table unchanged.

4. THE System SHALL protect `/admin/users/create` with `role_required("admin")` so that Teacher-role and Student-role sessions cannot reach this route.

5. THE System SHALL include a CSRF token on the user-creation form and validate it on POST; IF the CSRF token is absent or invalid, THEN THE System SHALL return HTTP 400 without inserting a row.

6. WHILE a Student visits `/register`, THE System SHALL create the new account with `role_name = 'student'` only, regardless of any role value supplied in the POST body, preserving the existing security constraint in `routes/auth.py`.

7. WHEN the Admin views `/admin/users`, THE System SHALL display each user's `full_name`, `username`, `email`, `role_name`, `school_name`, and `created_at`, ordered by `role_name` then `full_name`.

---

### Requirement 3: Admin Settings Management

**User Story:** As an Admin, I want to update the mastery threshold for each learning outcome from the settings page, so that pass marks can be adjusted to reflect curriculum changes without code deployments.

#### Acceptance Criteria

1. WHEN an Admin submits a valid POST request to `/admin/settings/threshold/<outcome_id>` with an integer `mastery_threshold` value between 1 and 100 inclusive, THE System SHALL update `learning_outcomes.mastery_threshold` for that `outcome_id` in PostgreSQL, insert an `audit_logs` row recording `actor_id`, `action = 'update_mastery_threshold'`, `entity_type = 'learning_outcomes'`, `entity_id = outcome_id`, and `details` containing the old and new threshold values, then redirect to `/admin/settings` with a success flash message.

2. WHEN an Admin submits a POST request to `/admin/settings/threshold/<outcome_id>` with a `mastery_threshold` value outside the range 1–100 or a non-integer value, THE System SHALL reject the update, return an error flash message, and leave `learning_outcomes.mastery_threshold` unchanged.

3. WHEN an Admin submits a POST request to `/admin/settings/threshold/<outcome_id>` for an `outcome_id` that does not exist in `learning_outcomes`, THE System SHALL return HTTP 404 without modifying any row.

4. THE System SHALL protect `/admin/settings/threshold/<outcome_id>` with `role_required("admin")`.

5. THE System SHALL include a CSRF token on the threshold-update form and validate it on POST.

6. WHEN an Admin views `/admin/settings`, THE System SHALL display each learning outcome's `subject_name`, `outcome_code`, `outcome_name`, and current `mastery_threshold` alongside an inline edit form, ordered by `subject_name` then `sequence_order`.

---

### Requirement 4: Offline-First Assessment Sync

**User Story:** As a Student using the application in a low-bandwidth or offline environment, I want my assessment submissions to be saved locally and automatically replayed to the server when connectivity is restored, so that my learning evidence is never lost due to network interruptions.

#### Acceptance Criteria

1. WHEN the ServiceWorker intercepts a POST request to `/assessment/<assessment_id>/submit` and the browser has no network connectivity, THE System SHALL store the full request payload (including `assessment_id`, all `question_<id>` form field values, and the CSRF token) as a JSON object in IndexedDB under the store name `'offlineQueue'` with a timestamp and `status = 'pending'`, and SHALL display a browser notification or UI banner informing the Student that the submission has been queued for sync.

2. WHEN the ServiceWorker detects that network connectivity is restored (via the browser `online` event), THE System SHALL iterate over all records in IndexedDB `'offlineQueue'` with `status = 'pending'` and replay each as a POST request to `/sync` in the order the records were created (oldest first).

3. WHEN THE System processes a POST request to `/sync` containing an `offline_sync_queue` payload array, THE System SHALL validate that `session['role'] == 'student'` and that each item's `learner_id` matches `session['user_id']`; IF either condition fails, THEN THE System SHALL return HTTP 403 without writing any data.

4. WHEN the `/sync` Flask route receives a valid payload item with `event_type = 'assessment_submission'`, THE System SHALL execute the same assessment-grading logic used by `POST /assessment/<assessment_id>/submit`, including scoring, `update_concept_mastery()`, `update_bkt_record()`, mastery record upsert, and `activity_logs` insert, all within a single database transaction.

5. WHEN the `/sync` Flask route successfully processes a payload item, THE System SHALL insert a corresponding row into `offline_sync_queue` with `sync_status = 'Synced'` and `synced_at = NOW()`, and SHALL return a JSON response `{"synced": <count>}` with HTTP 200.

6. IF an exception occurs while the `/sync` route processes a payload item, THEN THE System SHALL roll back that item's transaction, insert a row into `offline_sync_queue` with `sync_status = 'Failed'` and the error detail in `payload`, and continue processing remaining items without aborting the entire sync batch.

7. WHEN the ServiceWorker receives a successful HTTP 200 response from `/sync` for a queued item, THE System SHALL update that IndexedDB record's `status` to `'synced'` so it is not replayed again.

8. THE System SHALL exempt the `/sync` route from standard same-page CSRF validation by accepting the CSRF token from the JSON request body field `csrf_token` and validating it using Flask-WTF's `validate_csrf()` function.

9. WHEN a Student's browser is offline and the Student navigates to a page that requires dynamic data, THE ServiceWorker SHALL return the cached static assets (CSS files listed in `STATIC_ASSETS`) from the `'learn2master-v8-offline'` cache and allow page rendering to degrade gracefully, without returning stale HTML for dynamic routes.

---

### Requirement 5: Teacher Proactive Interventions

**User Story:** As a Teacher, I want to assign an intervention directly to a learner from the learner detail page, independent of the AI recommendation flow, so that I can act on my own professional judgement when I observe a learner struggling with a specific outcome.

#### Acceptance Criteria

1. WHEN a Teacher submits a valid POST request to `/teacher/learners/<learner_id>/intervene` with `intervention_type`, `intervention_note`, and `target_outcome_id`, THE System SHALL insert a new row into `teacher_interventions` with `teacher_id = session['user_id']`, `learner_id = learner_id`, `outcome_id = target_outcome_id`, `intervention_type`, `intervention_note`, and `status = 'Assigned'`, then redirect to `/teacher/learners/<learner_id>` with a success flash message.

2. WHEN a Teacher submits a POST request to `/teacher/learners/<learner_id>/intervene` with a missing or blank `intervention_type` or `intervention_note`, THE System SHALL reject the submission with an error flash message and redirect back to the learner detail page without inserting a row.

3. WHEN a Teacher submits a POST request to `/teacher/learners/<learner_id>/intervene` with a `target_outcome_id` that does not exist in `learning_outcomes`, THE System SHALL return HTTP 404 without inserting a row.

4. WHEN a Teacher submits a POST request to `/teacher/learners/<learner_id>/intervene` with a `learner_id` that does not correspond to a user with `role_name = 'student'`, THE System SHALL return HTTP 404 without inserting a row.

5. THE System SHALL protect `/teacher/learners/<learner_id>/intervene` with `role_required("teacher", "admin")` so that Student-role sessions cannot assign interventions.

6. THE System SHALL include a CSRF token on the intervention form and validate it on POST; IF the CSRF token is absent or invalid, THEN THE System SHALL return HTTP 400 without inserting a row.

7. WHEN a Teacher views `/teacher/learners/<learner_id>`, THE System SHALL display a form for assigning a new intervention and a list of all existing `teacher_interventions` rows for that learner, showing `outcome_name`, `intervention_type`, `intervention_note`, `status`, and `created_at`, ordered by `created_at` DESC.

8. WHEN a Teacher views `/teacher/learners/<learner_id>`, THE System SHALL also display the learner's mastery summary per outcome, including `pretest_score`, `practice_score`, `posttest_score`, `mastery_score`, and `mastery_status`, so the Teacher has evidence context when assigning an intervention.

9. THE System SHALL record a row in `activity_logs` with `activity_type = 'Teacher Intervention Assigned'` and `activity_description` identifying the `learner_id`, `outcome_id`, and `intervention_type` each time an intervention is successfully inserted.
