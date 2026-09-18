# CRM & Invoice Management System

A production-oriented CRM, customer management, invoice tracking, payment
tracking, and automated invoice reminder system.

- **Backend:** Python, FastAPI, SQLAlchemy 2.x (async), Alembic
- **Database:** PostgreSQL, hosted on **Supabase**
- **Auth:** custom JWT (access + revocable refresh tokens), bcrypt password hashing
- **Frontend:** React (Vite), Tailwind CSS, TanStack Query
- **Background jobs:** Celery + Redis (worker + beat)
- **Docs:** OpenAPI/Swagger via FastAPI at `/api/v1/docs`

See the architecture write-up (shared separately) for the full ERD, invoice
status engine, payment workflow, and reminder-deduplication design.

## Project status

**Phase 7 — Invoices.** CRUD + line items under `/invoices`, either
created directly or converted from an accepted quote
(`POST /invoices/from-quote/{quote_id}`), which copies the quote's items,
carries its customer/notes across, marks the quote `converted`, and
defaults `due_date` from `company_settings.payment_terms_days` when not
given explicitly. Line-item pricing math (`build_line_items` in
`app/services/pricing.py`) is now shared between quotes and invoices
rather than duplicated. Manual status transitions are limited to
`draft → sent/void` and `sent/overdue → void`; `partially_paid`, `paid`,
and `overdue` are reserved for the payment-recording and invoice-status-
engine phases that follow, not settable directly through the API.

## Why Supabase, and how it's wired in

Supabase is used purely as **managed Postgres** — not Supabase Auth, not
Row Level Security. The FastAPI backend owns its own `users` table, JWT
issuance, and role-based access control (ADMIN/MANAGER/STAFF/VIEWER) in the
service layer, since RLS policies would duplicate that logic with no
benefit here (the API is the only DB client).

Two connection strings are required because Supabase's connection pooler
runs in **transaction mode** on port 6543, which doesn't reliably support
the prepared statements/DDL that Alembic issues:

- `DATABASE_URL` — app runtime traffic, via the **transaction pooler** (6543)
- `DATABASE_URL_MIGRATIONS` — Alembic only, via the **session pooler /
  direct connection** (5432)

## Getting started

### 1. Create a Supabase project

Create a project at supabase.com, then grab both connection strings from
**Project Settings → Database → Connection string** (choose "Transaction
pooler" for the first, "Session pooler" or direct for the second).

### 2. Configure environment

```bash
cp .env.example .env
# edit .env: paste in your Supabase connection strings, set JWT_SECRET, SMTP creds
```

### 3. Run with Docker Compose

```bash
docker compose up --build
```

This starts Redis, the FastAPI backend, a Celery worker, Celery beat, and
the React frontend. Postgres is **not** started locally — the backend talks
directly to Supabase.

- Backend: http://localhost:8000/api/v1/docs
- Frontend: http://localhost:5173
- Health check: http://localhost:8000/health

### 4. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 5. Local development without Docker (backend)

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 6. Local development without Docker (frontend)

```bash
cd frontend
npm install
npm run dev
```

### 7. Running Celery manually

```bash
cd backend
celery -A celery_app.celery_app worker --loglevel=info
celery -A celery_app.celery_app beat --loglevel=info
```

### 8. Running tests

```bash
cd backend
pytest
```

## API endpoints

All routes are versioned under `/api/v1` (see `/api/v1/docs` for the live,
authoritative schema). Every route except `/auth/login` and `/auth/refresh`
requires a bearer access token; role-restricted routes are noted below.

- **Auth** — `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`,
  `GET /auth/me`
- **Users** (ADMIN only) — `POST /users`, `GET /users`, `GET /users/{id}`,
  `PATCH /users/{id}`
- **Customers** — `POST /customers`, `GET /customers`,
  `GET /customers/{id}`, `PATCH /customers/{id}`,
  `POST /customers/{id}/deactivate`. Reads: any role. Writes:
  ADMIN/MANAGER/STAFF. Deactivate: ADMIN/MANAGER.
- **Products** — same shape and role rules as Customers, under `/products`.
- **Quotes** — `POST /quotes`, `GET /quotes`, `GET /quotes/{id}`,
  `PATCH /quotes/{id}` (draft only), `DELETE /quotes/{id}` (draft only),
  `POST /quotes/{id}/send`, `/accept`, `/reject`, `/expire`. Reads: any
  role. Writes/transitions: ADMIN/MANAGER/STAFF.
- **Invoices** — `POST /invoices`, `POST /invoices/from-quote/{quote_id}`
  (accepted quotes only), `GET /invoices`, `GET /invoices/{id}`,
  `PATCH /invoices/{id}` (draft only), `DELETE /invoices/{id}` (draft
  only), `POST /invoices/{id}/send`, `POST /invoices/{id}/void`. Reads:
  any role. Writes/send: ADMIN/MANAGER/STAFF. Void: ADMIN/MANAGER.

Payments and reporting endpoints land in later phases (see Roadmap
below).

## Environment variables

See `.env.example` for the full list: database URLs, JWT settings, Redis
URL, SMTP credentials, company defaults, and CORS origins. Never commit
`.env`.

## Repository layout

```
backend/   FastAPI app, services, repositories, Celery tasks, Alembic migrations
frontend/  React + Vite + Tailwind SPA
docker-compose.yml
.env.example
```

## Roadmap (development phases)

1. Architecture & project setup ✅
2. Database & models ✅
3. Authentication & users ✅
4. Customer management ✅
5. Products/services ✅
6. Quotes ✅
7. Invoices ✅
8. Payments
9. Invoice status engine
10. Email service
11. Automated reminders
12. PDF invoices
13. Dashboard
14. Reports
15. Frontend polish
16. Testing
17. Dockerization (base already in place)
18. Deployment documentation
