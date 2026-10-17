"""Local-only browser QA API; capture queued emails without sending them.

Run from the repo root with backend's Python. Pair with Vite on :5174 and
VITE_API_BASE_URL=http://localhost:8002/api/v1. Uses .env.local only.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["YGT_ENV_FILE"] = str(ROOT / ".env.local")
os.environ["DEBUG"] = "false"
os.environ["PLATFORM_ADMIN_EMAILS"] = "demo.admin@example.com"
os.environ["FRONTEND_URL"] = "http://localhost:5174"
os.environ["CORS_ORIGINS"] = '["http://localhost:5174"]'

from app.core.config import settings
from urllib.parse import urlsplit

assert urlsplit(settings.DATABASE_URL).hostname in ("localhost", "127.0.0.1"), "Local database required"

from celery.app.task import Task

OUT = ROOT / "e2e" / "out-ticket-qa"
OUT.mkdir(exist_ok=True)


def capture(self, *args, **kwargs):
    with (OUT / "queued-emails.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"task": self.name, "args": args}, default=str) + "\n")


Task.delay = capture

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002)
