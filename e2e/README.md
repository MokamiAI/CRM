# Browser tests

Chrome-driven checks of a **local** YGT. Both scripts refuse to run against
anything but `localhost`.

| Script | What it checks |
| --- | --- |
| `app.mjs` | Signs in as the demo admin, opens every app page (laptop and phone), fails on page errors, API 5xx, "couldn't load" messages or sideways scrolling, saves screenshots, and accepts a quote on screen through to its draft invoice |
| `public.mjs` | Every button and link on the signed-out site: header, hero, business types, calculator, pricing and plan buttons, FAQ, footer, phone tap sizes |

## Running them

### Ticket workflow (isolated local email capture)

After migrating the local database and seeding the demo account, run these
from the repository root in separate terminals (PowerShell):

```powershell
backend/.venv312/Scripts/python.exe e2e/ticket-qa-server.py
```

```powershell
$env:VITE_API_BASE_URL='http://localhost:8002/api/v1'
cd frontend
npm.cmd run dev -- --port 5174
```

```powershell
node e2e/tickets.mjs
```

The QA API listens only on loopback, requires a local database, grants the
demo account platform admin access in that process, and captures Celery
tasks in `e2e/out-ticket-qa/queued-emails.jsonl` instead of sending email.
The browser test opens Chrome, submits a ticket with a file, checks its
download, sends a predefined reply, saves templates, changes status,
checks the customer's timeline and captured email, and takes desktop and
phone screenshots. Chrome stays open for review. Test tickets remain in
the local demo account. Stop both servers when finished.

### General app and public-site regression

For the MCEM sales-to-value workflow, use the isolated QA API/Vite commands
above, then run `node e2e/mcem.mjs` from the repo root. It exercises enablement,
stage blocking, evidence selection and confirmation, a Won customer journey,
value review, separate expansion, reporting and desktop/phone layouts. See
`MCEM.md` for the pilot's operating rules and scope. No production deployment
is part of this pilot.

```sh
scripts/dev-db.sh start                # local PostgreSQL on :5433
scripts/dev-backend.sh                 # API on :8000, against .env.local
(cd frontend && npm run build && npx vite preview --port 4173)
(cd backend && YGT_ENV_FILE=../.env.local python scripts/seed_demo.py)   # once
cd e2e && npm install
node app.mjs out        # screenshots in e2e/out
node public.mjs
```

`app.mjs` changes the demo data (it accepts a quote), so reseed from an
empty `ygt_dev` for a clean run. Set `CHROME_PATH` if Chrome is installed
elsewhere.
