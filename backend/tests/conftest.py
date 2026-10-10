import os

# app.core.config reads these at import time. Creating the async engine
# doesn't connect, so tests that never touch the DB run without Postgres.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DATABASE_URL_MIGRATIONS", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
