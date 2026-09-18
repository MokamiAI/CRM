# CRM & Invoice Management System

A production-oriented CRM, customer management, invoice tracking, payment
tracking, and automated invoice reminder system.

- **Backend:** Python, FastAPI, SQLAlchemy 2.x (async), Alembic
- **Database:** PostgreSQL, hosted on **Supabase**
- **Auth:** custom JWT (access + revocable refresh tokens), bcrypt password hashing
- **Frontend:** React (Vite), Tailwind CSS, TanStack Query — mobile-first,
  and wrapped with **Capacitor** for native Android + iOS builds
- **Background jobs:** Celery + Redis (worker + beat)
- **Docs:** OpenAPI/Swagger via FastAPI at `/api/v1/docs`

See the architecture write-up (shared separately) for the full ERD, invoice
status engine, payment workflow, and reminder-deduplication design.

## Project status

**Phase 9 — Invoice status engine.** `POST /invoices/refresh-overdue`
(ADMIN/MANAGER) flips `sent`/`partially_paid` invoices whose `due_date`
has passed to `overdue`; the same logic runs automatically on the
existing hourly Celery beat entry (`app/tasks/invoice_tasks.py`), so
manual and scheduled refreshes share one implementation.

Alongside this phase, company-level settings gained outgoing-email
configuration: `GET`/`PATCH /settings` (ADMIN only) now manage the
company's sending address and SMTP credentials (falling back to the
server-wide `SMTP_*` env vars when unset — see
`app/services/email_settings.py`), plus company info, branding, and
invoice/quote numbering, all previously only settable by editing `.env`
or the database directly. The frontend also gained the auth wiring
(login page, access/refresh-token interceptor, protected routes) needed
to reach any API route at all, plus a Settings page for the above.
Actually sending email through the configured account is Phase 10.

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

### 7. Building the Android / iOS apps

See [Mobile apps](#mobile-apps) below.

### 8. Running Celery manually

```bash
cd backend
celery -A celery_app.celery_app worker --loglevel=info
celery -A celery_app.celery_app beat --loglevel=info
```

### 9. Running tests

```bash
cd backend
pytest
```

## Mobile apps

The frontend is wrapped with [Capacitor](https://capacitorjs.com) so the
same React app also ships as native Android and iOS apps, in
`frontend/android/` and `frontend/ios/`. It isn't a separate codebase —
there's no mobile-specific UI to maintain; the native project is just a
thin shell that loads the same built web app, and gains access to native
device APIs if/when the app needs them (push notifications, camera, etc.).

The UI itself is mobile-first: a bottom tab bar below the `sm` breakpoint
(top nav above it), `safe-area-inset` padding for the iOS notch/home
indicator (`.safe-top`/`.safe-bottom` in `src/index.css`), 16px form
inputs (smaller triggers iOS's auto-zoom-on-focus), and
`viewport-fit=cover` in `index.html`.

### Before building for a phone

Native builds bundle the compiled web assets into the app at build
time — they don't talk to a live dev server, so `localhost` in
`VITE_API_BASE_URL` means the phone itself, not your machine. Point
`frontend/.env` (see `frontend/.env.example`) at your real,
**HTTPS**-reachable backend URL before running any of the commands
below; both platforms block plain `http://` outside of local emulator
testing. Also make sure your deployed backend's `CORS_ORIGINS` still
includes `capacitor://localhost` and `https://localhost` — the defaults
in `.env.example` already do.

```bash
cd frontend
npm install
npm run cap:sync   # vite build, then copies dist/ into android/ and ios/
```

### Android

Requires [Android Studio](https://developer.android.com/studio) (which
bundles the Android SDK). Any OS works, including this Windows dev
environment — but building/running still needs Android Studio installed
locally, which this sandbox does not have.

```bash
npm run android:open   # syncs, then opens android/ in Android Studio
```

From Android Studio: pick a device/emulator and hit Run to test, or
**Build → Generate Signed Bundle/APK** to produce a release `.aab` for
the Play Store (one-time $25 Play Console registration).

### iOS

**Requires a Mac with Xcode.** This is an Apple platform requirement,
not a limitation of any particular dev setup — Xcode does not run on
Windows or Linux, so the `ios/` project can be generated and version-
controlled from anywhere (as it has been here), but only actually opened,
built, and run from a Mac.

```bash
npm run ios:open   # syncs, then opens ios/App/App.xcodeproj in Xcode
```

From Xcode: select a simulator or a signed device to Run, or
**Product → Archive** to submit to TestFlight/the App Store (requires an
active $99/yr Apple Developer Program membership and a signing
certificate/provisioning profile).

### After changing the frontend

Any time you change `frontend/src/**`, re-run `npm run cap:sync` (or
`android:open`/`ios:open`, which sync first) before rebuilding the native
apps — Capacitor only copies the built web assets in on sync, it doesn't
watch for changes.

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
- **Payments** — `POST /invoices/{invoice_id}/payments`,
  `GET /invoices/{invoice_id}/payments`, `DELETE /payments/{id}`. Reads:
  any role. Record: ADMIN/MANAGER/STAFF. Delete (correction): ADMIN only.
- **Invoice status engine** — `POST /invoices/refresh-overdue`
  (ADMIN/MANAGER), also run automatically every hour by Celery beat.
- **Settings** (ADMIN only) — `GET /settings`, `PATCH /settings`: company
  info, invoice/quote numbering, payment terms, and outgoing email
  (sender address + SMTP host/port/username/password/TLS). `smtp_password`
  is write-only — omit it on PATCH to leave the stored value unchanged.

Reporting endpoints land in later phases (see Roadmap below).

## Environment variables

See `.env.example` for the full list: database URLs, JWT settings, Redis
URL, SMTP credentials, company defaults, and CORS origins. Never commit
`.env`. The frontend has its own `frontend/.env.example` (Vite reads
`.env` from the frontend directory, not the repo root) — see
[Mobile apps](#mobile-apps) for why its value matters for native builds.

## Repository layout

```
backend/           FastAPI app, services, repositories, Celery tasks, Alembic migrations
frontend/          React + Vite + Tailwind SPA
frontend/android/  Capacitor-generated native Android project
frontend/ios/      Capacitor-generated native Xcode project
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
8. Payments ✅
9. Invoice status engine ✅
10. Email service
11. Automated reminders
12. PDF invoices
13. Dashboard
14. Reports
15. Frontend polish
16. Testing
17. Dockerization (base already in place)
18. Deployment documentation
