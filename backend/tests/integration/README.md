# Integration tests

These run the real API against a real, migrated PostgreSQL database. CI runs
them on every push (see `.github/workflows/ci.yml`). Without a database they
are skipped, so `pytest` still works anywhere.

On a PC, with the local PostgreSQL from `scripts/dev-db.sh` running:

```sh
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres@localhost:5433/ygt_test
export DATABASE_URL_MIGRATIONS=$DATABASE_URL JWT_SECRET=test-secret
alembic upgrade head
pytest tests/integration
```

Never point `DATABASE_URL` at a live database: these tests create companies.
