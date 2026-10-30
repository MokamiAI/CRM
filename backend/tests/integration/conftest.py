"""Tests that run the real API against a real, migrated PostgreSQL database.

They run when DATABASE_URL points at one (CI starts a Postgres service; on a
PC: see README.md here) and are skipped otherwise, so the unit tests still run
anywhere. Never point DATABASE_URL at a live database: these tests create
companies.
"""
import os
import uuid

import pytest
import pytest_asyncio
from celery.app.task import Task
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.tenancy import set_system
from app.main import app
from app.models.user import User


async def _database_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1 FROM invoices LIMIT 1")
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def api(monkeypatch):
    if not await _database_ready():
        if os.environ.get("REQUIRE_TEST_DATABASE"):
            pytest.fail("REQUIRE_TEST_DATABASE is set but DATABASE_URL has no migrated database")
        pytest.skip("needs a migrated test database in DATABASE_URL")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    # Every background task queued (emails, reminders) is recorded instead
    # of sent, so a test can prove nothing went out.
    queued: list[tuple[str, tuple]] = []
    monkeypatch.setattr(Task, "delay", lambda self, *args, **kwargs: queued.append((self.name, args)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1") as client:
        client.queued = queued
        yield client
    # Connections belong to this test's event loop; the next test gets fresh ones.
    await engine.dispose()


ADDRESS = "12 Church Street, Polokwane, 0700"


async def mark_verified(email: str) -> None:
    """As if the person clicked the link in "Confirm your email"."""
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(User).where(User.email == email.lower()).values(email_verified_at=func.now()))
        await db.commit()


async def new_company(api: AsyncClient, name: str, plan: str = "grow") -> dict:
    """Signs a new company up on a trial of `plan`; returns its auth headers, email and id."""
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    res = await api.post(
        "/auth/register",
        json={"company_name": name, "full_name": "Test Owner", "email": email, "password": "Correct-Horse-9", "plan": plan, "business_address": ADDRESS, "accept_terms": True},
    )
    assert res.status_code == 201, res.text
    await mark_verified(email)
    async with AsyncSessionLocal() as db:
        set_system(db)
        user_id, company_id = (await db.execute(select(User.id, User.company_id).where(User.email == email))).one()
    return {
        "headers": {"Authorization": f"Bearer {res.json()['access_token']}"},
        "email": email,
        "user_id": user_id,
        "company_id": company_id,
    }
