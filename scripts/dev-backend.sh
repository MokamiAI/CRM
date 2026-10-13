#!/usr/bin/env bash
# The API on http://localhost:8000 against the local database, using
# .env.local (never the live database; see ALLOW_REMOTE_DATABASE in
# backend/app/core/config.py). Migrates first.
set -euo pipefail
cd "$(dirname "$0")/.."
export YGT_ENV_FILE="$PWD/.env.local"
py="$PWD/backend/.venv312/Scripts/python.exe"; [ -x "$py" ] || py=python
(cd backend && "$py" -m alembic upgrade head)
exec "$py" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
