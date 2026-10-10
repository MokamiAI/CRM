# CRM & Invoice Management System

A production-oriented CRM, customer management, invoice tracking, payment
tracking, and automated invoice reminder system.

- **Backend:** Python, FastAPI, SQLAlchemy 2.x (async), Alembic
- **Database:** PostgreSQL, hosted on **Supabase**
- **Auth:** custom JWT (access + revocable refresh tokens), bcrypt password hashing
- **Frontend:** React (Vite), Tailwind CSS, TanStack Query — mobile-first,
  and wrapped with **Capacitor** for native Android + iOS builds
- **Mobile app:** separate **Expo/React Native** app (`mobile/`) for live
  testing in **Expo Go** — see [Mobile apps](#mobile-apps) for why there
  are two mobile approaches in this repo
- **Background jobs:** Celery + Redis (worker + beat)
- **Docs:** OpenAPI/Swagger via FastAPI at `/api/v1/docs`

See the architecture write-up (shared separately) for the full ERD, invoice
status engine, payment workflow, and reminder-deduplication design.

## Project status

**CRM core (modelled on HubSpot / Pipedrive / Attio).** The app now has
the standard CRM object model around the billing core: **customers** are
the companies, with **contacts** (the people there, one primary);
**deals** move through a fixed pipeline (lead → qualified → proposal →
negotiation → won/lost) on a drag-and-drop board whose cards show each
deal's *next activity* (overdue / due today / nothing planned), the way
Pipedrive does; **activities** (calls, meetings, tasks, emails,
deadlines) with due dates form a daily work queue (Overdue / Today /
Upcoming / Done); **notes** capture history. Customer and deal pages use
HubSpot's three-column record layout (details · next steps + one
chronological timeline of notes, activities, deals, quotes, invoices,
payments and reminders · related records), and Ctrl/Cmd+K opens a
command palette that searches every record type (Attio/Linear-style).
Quotes can be linked to the deal they were written for.

**Phase 11 — Automated reminders.** Every morning at 07:00 (`DEFAULT_TIMEZONE`)
Celery beat emails a payment reminder to customers with unpaid
invoices (`sent`/`partially_paid`/`overdue`) once each reaches a step in
the company's reminder schedule: days relative to the due date, `-3, 0,
7, 14` by default, editable (and switchable off) under Settings → Payment
reminders. Each step is sent at most once per invoice, enforced by the
unique `(invoice_id, reminder_type)` constraint on `reminder_logs`: the
reminder is claimed in the database before the email is queued, so
overlapping runs can't duplicate it. Only the latest step reached is
sent, so a scheduler outage never produces a burst of stale reminders.
The email wording (due soon / due today / N days overdue) is worked out
when it's sent, and nothing is sent if the invoice was paid in the
meantime. Staff can also send a reminder by hand from an invoice, and
each invoice shows its reminder history.

**Phase 10 — Email service.** Customers are now emailed automatically
when an invoice or quote is sent (`POST /invoices/{id}/send`,
`POST /quotes/{id}/send`) and when a payment is recorded against their
invoice (a receipt showing the remaining balance). Each of those routes
takes `?notify=false` to skip the email. Messages are rendered from
Jinja templates in `app/templates/emails/` (HTML plus a plain-text
fallback) and sent by Celery tasks in `app/tasks/email_tasks.py` through
the company's SMTP settings, falling back to the server-wide `SMTP_*`
env vars. SMTP/network failures retry with backoff (up to 5 times);
customers with no email address, or a server with no SMTP configured,
are skipped with a log line rather than failing the request.
`POST /settings/test-email` (ADMIN) sends a test message synchronously
so a bad SMTP configuration shows up immediately, and the Settings page
has a button for it.

Previous phase: **Phase 9 — Invoice status engine.**
`POST /invoices/refresh-overdue` (ADMIN/MANAGER) flips
`sent`/`partially_paid` invoices whose `due_date` has passed to
`overdue`, and the same logic runs hourly on Celery beat. Company
settings (`GET`/`PATCH /settings`, ADMIN only) manage company info,
numbering, payment terms and the outgoing email account.

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
# -Q must list every queue in celery_app's task_routes, or tasks routed
# there (e.g. all emails) are never picked up.
celery -A celery_app.celery_app worker --loglevel=info -Q default,emails,reports
celery -A celery_app.celery_app beat --loglevel=info
```

### 9. Running tests

```bash
cd backend
pytest
```

## Mobile apps

There are **two** mobile approaches in this repo, because they solve
different problems:

- **`frontend/` + Capacitor** — the real long-term mobile app. Wraps the
  actual product UI for native Android/iOS builds and eventual App
  Store/Play Store submission. No separate UI to maintain.
- **`mobile/` (Expo/React Native)** — exists solely so **Expo Go** can be
  used for quick live testing on a phone. Expo Go cannot load the
  Capacitor/web app at all (different tech stack entirely — it only runs
  React Native), so this is a second, independent UI built with React
  Native components, hand-kept in sync with the same backend API and the
  same screens (login, dashboard, settings). It is not where new product
  features should go by default — that's `frontend/`. Reach for `mobile/`
  specifically when you want to iterate with Expo Go's instant reload on
  a physical phone without any native build step.

### Capacitor (`frontend/`)

Wraps the existing React app so the same UI also ships as native Android
and iOS apps, in `frontend/android/` and `frontend/ios/`. It isn't a
separate codebase — there's no mobile-specific UI to maintain; the native
project is just a thin shell that loads the same built web app, and gains
access to native device APIs if/when the app needs them (push
notifications, camera, etc.).

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

### Expo / Expo Go (`mobile/`)

Install the [Expo Go](https://expo.dev/go) app on your phone (App
Store/Play Store — this one you actually can download today), then:

```bash
cd mobile
npm install
cp .env.example .env
# edit .env: set EXPO_PUBLIC_API_BASE_URL to your machine's LAN IP
#   (e.g. http://10.10.49.51:8000/api/v1) or a real deployed backend —
#   never "localhost", which means the phone itself here, not your machine
npm start
```

Scan the QR code Metro prints with Expo Go (Android: in-app scanner;
iOS: system Camera app), with your phone on the **same Wi-Fi network** as
your dev machine. Edits to `mobile/src/**` hot-reload on the phone
immediately — no rebuild, no Xcode, no Android Studio.

No `CORS_ORIGINS` changes needed here, unlike the Capacitor app: CORS is
a browser same-origin policy, enforced by the WebView the Capacitor app
runs in — Expo Go's networking goes through native HTTP APIs instead, so
the backend's CORS allowlist simply doesn't apply to it.

This app deliberately duplicates only what's needed for parity with the
web app's current screens (login, dashboard placeholder, settings form)
using React Native components (`View`/`TextInput`/`StyleSheet`) instead
of the web app's Tailwind/DOM — a genuinely different UI layer, not a
config variant. Keep both in sync by hand when either changes.

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
- **CRM** — `GET/POST /customers/{id}/contacts`, `PATCH/DELETE
  /contacts/{id}`; `GET/POST /deals` (`?status=open|won|lost|all`,
  `?mine=true`), `GET/PATCH /deals/{id}`, `DELETE /deals/{id}`
  (ADMIN/MANAGER), `GET /deals/{id}/timeline`, `GET /deals/{id}/quotes`;
  `GET/POST /activities` (`?scope=overdue|today|upcoming|done|all`,
  `?mine=true`), `GET /activities/counts`, `PATCH/DELETE
  /activities/{id}`; `GET/POST /notes`, `DELETE /notes/{id}` (author or
  ADMIN); `GET /customers/{id}/timeline`; `GET /search?q=`; `GET /team`
  (active users, names only); `GET /company` (name/currency/logo for any
  signed-in user). Reads: any role. Writes: ADMIN/MANAGER/STAFF.
- **Reminders** — `POST /invoices/send-reminders` (ADMIN/MANAGER) runs
  the daily reminder pass now (same logic as the 07:00 beat job; safe to
  repeat), `POST /invoices/{id}/remind` (ADMIN/MANAGER/STAFF) sends one
  immediately, `GET /invoices/{id}/reminders` lists what was sent. The
  schedule is `reminders_enabled` + `reminder_offsets` on `/settings`.
- **Settings** (ADMIN only) — `GET /settings`, `PATCH /settings`: company
  info, invoice/quote numbering, payment terms, and outgoing email
  (sender address + SMTP host/port/username/password/TLS). `smtp_password`
  is write-only — omit it on PATCH to leave the stored value unchanged.
  `POST /settings/test-email` (optional body `{"to": "..."}`, defaults to
  the admin's own address) sends a test message with the saved settings.
- **Customer emails** — `POST /invoices/{id}/send`, `POST /quotes/{id}/send`
  and `POST /invoices/{id}/payments` email the customer by default; pass
  `?notify=false` to skip it.

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
frontend/          React + Vite + Tailwind SPA (the product UI)
frontend/android/  Capacitor-generated native Android project
frontend/ios/      Capacitor-generated native Xcode project
mobile/            Separate Expo/React Native app, for Expo Go testing only
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
10. Email service ✅
11. Automated reminders ✅
12. PDF invoices
13. Dashboard
14. Reports
15. Frontend polish
16. Testing
17. Dockerization (base already in place)
18. Deployment documentation
