# Browser tests

Chrome-driven checks of a **local** YGT. Both scripts refuse to run against
anything but `localhost`.

| Script | What it checks |
| --- | --- |
| `app.mjs` | Signs in as the demo admin, opens every app page (laptop and phone), fails on page errors, API 5xx, "couldn't load" messages or sideways scrolling, saves screenshots, and accepts a quote on screen through to its draft invoice |
| `public.mjs` | Every button and link on the signed-out site: header, hero, business types, calculator, pricing and plan buttons, FAQ, footer, phone tap sizes |

## Running them

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
