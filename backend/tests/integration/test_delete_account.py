"""Anyone who can sign up can delete their account. The only admin takes the
company with them; anyone else leaves it, their details erased."""
import uuid

import pytest

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.models.company_settings import CompanySettings
from app.models.user import User
from .conftest import new_company
from .test_team_tasks import _member

PASSWORD = "Correct-Horse-9"


async def company_exists(company_id) -> bool:
    async with AsyncSessionLocal() as db:
        set_system(db)
        return await db.get(CompanySettings, company_id) is not None


@pytest.mark.asyncio
async def test_the_only_admin_deletes_the_whole_company_after_confirming(api):
    owner = await new_company(api, "Gone Tomorrow Co")
    headers = owner["headers"]
    await api.post("/customers", json={"name": "A customer"}, headers=headers)
    assert (await api.get("/auth/delete-account", headers=headers)).json() == {"whole_company": True, "allowed": True}

    wrong_password = await api.post("/auth/delete-account", json={"password": "nope", "company_name": "Gone Tomorrow Co"}, headers=headers)
    assert wrong_password.status_code == 400 and wrong_password.json()["error_code"] == "PASSWORD_INCORRECT"
    wrong_name = await api.post("/auth/delete-account", json={"password": PASSWORD, "company_name": "Some Other Co"}, headers=headers)
    assert wrong_name.status_code == 400 and wrong_name.json()["error_code"] == "COMPANY_NAME_MISMATCH"
    assert await company_exists(owner["company_id"])

    done = await api.post("/auth/delete-account", json={"password": PASSWORD, "company_name": "gone tomorrow co "}, headers=headers)
    assert done.status_code == 200, done.text
    assert done.json() == {"deleted": "company"}
    assert not await company_exists(owner["company_id"])
    assert (await api.post("/auth/login", json={"email": owner["email"], "password": PASSWORD})).status_code == 401


@pytest.mark.asyncio
async def test_a_team_member_leaves_and_the_company_carries_on(api):
    owner = await new_company(api, "Stays Open Co")
    staff, staff_id = await _member(api, owner)
    assert (await api.get("/auth/delete-account", headers=staff)).json()["whole_company"] is False
    done = await api.post("/auth/delete-account", json={"password": PASSWORD}, headers=staff)
    assert done.status_code == 200 and done.json() == {"deleted": "account"}
    async with AsyncSessionLocal() as db:
        set_system(db)
        gone = await db.get(User, uuid.UUID(staff_id))
        assert gone.full_name == "Deleted user" and gone.email.endswith("@deleted.invalid") and not gone.is_active
    assert await company_exists(owner["company_id"])
    assert (await api.get("/customers", headers=owner["headers"])).status_code == 200


@pytest.mark.asyncio
async def test_an_admin_with_another_admin_only_removes_themselves(api):
    owner = await new_company(api, "Two Admins Co")
    second, _ = await _member(api, owner, "admin")
    assert (await api.get("/auth/delete-account", headers=second)).json()["whole_company"] is False
    assert (await api.post("/auth/delete-account", json={"password": PASSWORD}, headers=second)).json() == {"deleted": "account"}
    assert await company_exists(owner["company_id"])


@pytest.mark.asyncio
async def test_ygt_admins_cannot_delete_themselves_here(api, monkeypatch):
    owner = await new_company(api, "YGT Itself")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", owner["email"])
    assert (await api.get("/auth/delete-account", headers=owner["headers"])).json()["allowed"] is False
    refused = await api.post("/auth/delete-account", json={"password": PASSWORD, "company_name": "YGT Itself"}, headers=owner["headers"])
    assert refused.status_code == 409
    assert await company_exists(owner["company_id"])
