# Learn2Master V8 — Supabase Edition

AI-enabled Information System prototype for mastery-based learning under Uganda's CBC.  
**MSc Dissertation:** An AI-Enabled Framework for Mastery-Based Learning under CBC  
**Stack:** Python · Flask · Supabase (PostgreSQL + Storage) · psycopg2 · Flask-WTF

---

## Quick Start

### 1. Clone & install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) → New Project
2. Note your **Project URL**, **anon key**, **service role key**
3. Go to **Project Settings → Database → Connection string (Transaction pooler, port 6543)**

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your Supabase credentials:

```env
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
FLASK_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
SUPABASE_URL=https://[ref].supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
```

### 4. Initialise the database

Run `database_v2_postgres.sql` in the **Supabase SQL Editor**  
(Dashboard → SQL Editor → paste contents → Run):

```
database_v2_postgres.sql       ← tables, indexes, triggers, RLS, seed roles/schools/subjects
database_functions_postgres.sql ← PostgreSQL utility functions (dashboard stats, BKT, etc.)
supabase_storage_setup.sql     ← Storage bucket RLS policies (after creating the bucket)
```

### 5. Create the Supabase Storage bucket

Dashboard → Storage → New Bucket  
- **Name:** `practical-evidence`  
- **Public:** No

### 6. Seed curriculum data

```bash
python seed_data.py
```

### 7. Run the application

```bash
python app.py
```

Open: `http://127.0.0.1:5000`

---

## Demo Accounts

| Role    | Username  | Password |
|---------|-----------|----------|
| Student | `elijah`  | `12345`  |
| Teacher | `teacher` | `12345`  |
| Admin   | `admin`   | `12345`  |

---

## Project Structure

```
learn2master_v8_dissertation_final/
├── app.py                          # Flask app factory, CSRF, blueprints
├── database.py                     # psycopg2 connection pool (replaces sqlite3)
├── requirements.txt                # Dependencies
├── .env.example                    # Environment variable template (copy to .env)
├── .gitignore
│
├── database_v2_postgres.sql        # ← Run first: full PostgreSQL schema + RLS
├── database_functions_postgres.sql # ← Run second: PG functions for performance
├── supabase_storage_setup.sql      # ← Run third: Storage bucket RLS policies
├── init_db.py                      # Python runner for the SQL schema file
├── seed_data.py                    # Curriculum content + demo users
│
├── routes/                         # Flask blueprints (all migrated to psycopg2)
│   ├── auth.py                     # Login, register, logout
│   ├── dashboard.py
│   ├── learning.py                 # Adaptive engine: pretest→practice→posttest
│   ├── mastery.py
│   ├── student.py
│   ├── teacher.py
│   ├── admin.py
│   ├── analytics.py
│   ├── research.py
│   ├── subjects.py, courses.py, framework.py, profile.py
│   └── guards.py                   # @login_required, @role_required decorators
│
├── services/                       # Pure Python AI/engine services
│   ├── mastery_engine.py           # Evidence-based mastery calculation
│   ├── bkt_engine.py               # Bayesian Knowledge Tracing
│   ├── recommendation_engine.py    # Explainable AI recommendations
│   ├── evidence_engine.py          # Reflection & evidence checklist queries
│   ├── ai_explainability_engine.py # AI decision explanation builder
│   ├── analytics_engine.py         # Teacher/research analytics queries
│   ├── learner_profile_engine.py   # Learner profile assembly
│   ├── framework_alignment.py      # CBC component alignment (static)
│   └── offline_engine.py           # Offline sync queue
│
├── templates/                      # Jinja2 HTML templates (CSRF tokens on all forms)
└── static/                         # CSS, JS, service worker
```

---

## Key Features

- **Sequential mastery locking** — outcome 2 unlocks only after outcome 1 is mastered
- **Evidence-based mastery** — pre-test + adaptive practice + reflection + practical evidence + post-test
- **Bayesian Knowledge Tracing** — per-concept probability updated on every question answer
- **Explainable AI** — every recommendation includes reason, weak concepts, and evidence used
- **Teacher-in-the-loop** — approve/override AI recommendations, review practical evidence
- **Role-based access** — student / teacher / admin with `@role_required` guards
- **CSRF protection** — all POST forms protected via Flask-WTF
- **Supabase RLS** — row-level security on all learner data tables
- **Supabase Storage** — practical evidence files stored in private bucket
- **Connection pooling** — psycopg2 SimpleConnectionPool (1–10 connections)
- **Research dashboard** — Chapter 4 dissertation metrics (BKT, mastery gain, evidence counts)

---

## Documentation

See `docs/` folder:

- `SUPABASE_MIGRATION_REPORT.md` — complete migration analysis and fix log
- `V8_FINAL_ALIGNMENT.md` — proposal alignment
- `FINAL_PROPOSAL_ALIGNMENT.md` — feature traceability
- `V8_TRACEABILITY_MATRIX.md` — evaluation indicators

---

## Security Notes

- **Never commit `.env`** — it contains your Supabase service key
- The Flask backend uses the **service role key** which bypasses RLS — this is correct and intentional. RLS guards against direct PostgREST/JS API abuse
- Rotate `FLASK_SECRET_KEY` before any deployment: `python -c "import secrets; print(secrets.token_hex(32))"`
- Registration is locked to the `student` role — create teacher/admin accounts via the Admin panel
