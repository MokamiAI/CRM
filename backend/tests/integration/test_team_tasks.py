"""Team tasks and notifications: assigning a task tells the assignee; the
assignee reports back (Done and Blocked need a note), which tells whoever
assigned it; activities falling due remind their owner a minute before,
once; and the bell lists it all."""
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.models.crm import Activity
from app.tasks.notification_tasks import remind_company

from .conftest import mark_verified, new_company

SAST = ZoneInfo("Africa/Johannesburg")


async def _member(api, admin: dict, role: str = "staff") -> tuple[dict, str]:
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    res = await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": "Lerato Dube", "role": role}, headers=admin["headers"])
    assert res.status_code == 201, res.text
    await mark_verified(email)
    login = await api.post("/auth/login", json={"email": email, "password": "Correct-Horse-9"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, res.json()["id"]


async def _bell(api, headers) -> dict:
    res = await api.get("/notifications", headers=headers)
    assert res.status_code == 200, res.text
    # Leaves out YGT's one marketing question (test_user_marketing_consent).
    bell = res.json()
    asked = [n for n in bell["items"] if n["kind"] == "marketing_consent"]
    return {
        "unread": bell["unread"] - sum(n["read_at"] is None for n in asked),
        "items": [n for n in bell["items"] if n["kind"] != "marketing_consent"],
    }


@pytest.mark.asyncio
async def test_assign_report_back_and_hear_about_it(api):
    owner = await new_company(api, "Tasks Catering")
    staff, staff_id = await _member(api, owner)
    before = len(api.queued)

    # The owner gives Lerato a task.
    task = await api.post(
        "/activities",
        json={"type": "task", "subject": "Order the tent", "due_date": (date.today() + timedelta(days=2)).isoformat(), "owner_id": staff_id},
        headers=owner["headers"],
    )
    assert task.status_code == 201, task.text
    task = task.json()
    assert task["status"] == "todo" and task["created_by"] == str(owner["user_id"])

    # The owner sees it under "handed out"; Lerato sees it as hers.
    handed = (await api.get("/activities", params={"handed_out": True}, headers=owner["headers"])).json()
    assert [x["id"] for x in handed] == [task["id"]]
    assert [x["id"] for x in (await api.get("/activities", params={"mine": True}, headers=staff)).json()] == [task["id"]]

    # Lerato hears about it: behind the bell, and by email.
    bell = await _bell(api, staff)
    assert bell["unread"] == 1 and bell["items"][0]["kind"] == "task_assigned"
    assert bell["items"][0]["params"]["subject"] == "Order the tent"
    assert any(name.endswith("send_platform_email_task") for name, _ in api.queued[before:])
    # The person who assigned it isn't notified of their own action.
    assert (await _bell(api, owner["headers"]))["unread"] == 0

    url = f"/activities/{task['id']}/updates"
    # Done or Blocked without a word is refused.
    bad = await api.post(url, json={"status": "done"}, headers=staff)
    assert bad.status_code == 409 and bad.json()["error_code"] == "TASK_NOTE_REQUIRED"
    assert (await api.post(url, json={}, headers=staff)).json()["error_code"] == "TASK_UPDATE_EMPTY"

    # In progress, then done with a note: the task follows.
    assert (await api.post(url, json={"status": "in_progress"}, headers=staff)).status_code == 201
    done = await api.post(url, json={"status": "done", "note": "Booked with Party Hire, delivered Friday 08:00."}, headers=staff)
    assert done.status_code == 201, done.text
    after = next(a for a in (await api.get("/activities", params={"scope": "all"}, headers=owner["headers"])).json() if a["id"] == task["id"])
    assert after["status"] == "done" and after["done"] is True and after["done_at"]

    # The owner hears each update; the thread keeps them in order.
    bell = await _bell(api, owner["headers"])
    assert bell["unread"] == 2 and {n["kind"] for n in bell["items"]} == {"task_update"}
    assert bell["items"][0]["params"]["note"] == "Booked with Party Hire, delivered Friday 08:00."
    thread = (await api.get(url, headers=owner["headers"])).json()
    assert [(u["status"], u["note"]) for u in thread] == [("in_progress", None), ("done", "Booked with Party Hire, delivered Friday 08:00.")]

    # Read: the count drops.
    assert (await api.post("/notifications/read", json={}, headers=owner["headers"])).status_code == 204
    assert (await _bell(api, owner["headers"]))["unread"] == 0

    # Viewers can't report on tasks; other companies can't see them.
    viewer, _ = await _member(api, owner, "viewer")
    assert (await api.post(url, json={"note": "hi"}, headers=viewer)).status_code == 403
    other = await new_company(api, "Elsewhere")
    assert (await api.get(url, headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_reassigning_tells_the_new_person_and_ticking_done_keeps_status(api):
    owner = await new_company(api, "Reassign Co")
    staff, staff_id = await _member(api, owner)
    mine = (await api.post("/activities", json={"subject": "Call Naledi", "due_date": date.today().isoformat()}, headers=owner["headers"])).json()
    assert (await _bell(api, staff))["unread"] == 0  # own task: nobody told
    await api.patch(f"/activities/{mine['id']}", json={"owner_id": staff_id}, headers=owner["headers"])
    assert (await _bell(api, staff))["items"][0]["kind"] == "task_assigned"
    ticked = (await api.patch(f"/activities/{mine['id']}", json={"done": True}, headers=staff)).json()
    assert ticked["status"] == "done"
    unticked = (await api.patch(f"/activities/{mine['id']}", json={"done": False}, headers=staff)).json()
    assert unticked["status"] == "todo"


@pytest.mark.asyncio
async def test_a_reminder_a_minute_before_and_only_once(api):
    owner = await new_company(api, "Reminder Co")
    h = owner["headers"]
    today = date.today()
    soon = await api.post("/activities", json={"type": "call", "subject": "Call Thabo", "due_date": today.isoformat(), "due_time": "14:30"}, headers=h)
    later = await api.post("/activities", json={"type": "meeting", "subject": "Site visit", "due_date": today.isoformat(), "due_time": "16:00"}, headers=h)
    allday = await api.post("/activities", json={"subject": "Send the quote", "due_date": today.isoformat()}, headers=h)
    assert soon.status_code == later.status_code == allday.status_code == 201

    company = owner["company_id"]
    # Made today (before the 08:00 reminder time in this test's clock): it counts.
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(Activity).where(Activity.subject == "Send the quote").values(created_at=datetime.combine(today, time(7, 0), SAST)))
        await db.commit()
    # 14:28: one daily digest for the date-only task. 14:29: the call notice.
    assert await remind_company(company, datetime.combine(today, time(14, 28), SAST)) == 1  # daily task digest
    assert await remind_company(company, datetime.combine(today, time(14, 29), SAST)) == 1  # Call Thabo
    # Again a minute later: no repeats.
    assert await remind_company(company, datetime.combine(today, time(14, 30), SAST)) == 0
    bell = await _bell(api, h)
    subjects = [n["params"]["subject"] for n in bell["items"] if n["kind"] == "activity_due"]
    assert sorted(subjects) == ["Call Thabo"]
    digest = [n for n in bell["items"] if n["kind"] == "task_digest"]
    assert len(digest) == 1 and "Send the quote" in digest[0]["body"]
    call = next(n for n in bell["items"] if n["params"]["subject"] == "Call Thabo")
    assert call["params"]["time"] == "14:30" and call["title"] == "Due at 14:30: Call Thabo"

    # Long past (the server was off): not woken up about it.
    assert await remind_company(company, datetime.combine(today, time(18, 30), SAST)) == 0  # 16:00 + 2h passed
    # Done: no reminder.
    await api.patch(f"/activities/{later.json()['id']}", json={"done": True}, headers=h)
    assert await remind_company(company, datetime.combine(today, time(15, 59), SAST)) == 0


@pytest.mark.asyncio
async def test_devices_can_subscribe_to_push(api):
    owner = await new_company(api, "Push Co")
    h = owner["headers"]
    sub = {"endpoint": f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}", "keys": {"p256dh": "B" + "x" * 86, "auth": "a" * 22}}
    assert (await api.post("/notifications/push", json=sub, headers=h)).status_code == 204
    assert (await api.post("/notifications/push", json=sub, headers=h)).status_code == 204  # again: still one
    assert (await api.post("/notifications/push/remove", json={"endpoint": sub["endpoint"]}, headers=h)).status_code == 204
    settings = (await api.get("/notifications/push", headers=h)).json()
    assert set(settings) == {"enabled", "public_key"}
    assert (await api.post("/notifications/test", headers=h)).status_code == 202
    assert (await _bell(api, h))["items"][0]["kind"] == "test"


@pytest.mark.asyncio
async def test_no_due_today_ping_for_a_task_made_that_day(api):
    owner = await new_company(api, "Fresh Task Co")
    today = date.today()
    await api.post("/activities", json={"subject": "Made at lunchtime", "due_date": today.isoformat()}, headers=owner["headers"])
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(Activity).where(Activity.subject == "Made at lunchtime").values(created_at=datetime.combine(today, time(12, 0), SAST)))
        await db.commit()
    # Made at 12:00 on its day, after the 08:00 reminder time: they already know.
    assert await remind_company(owner["company_id"], datetime.combine(today, time(23, 0), SAST)) == 0
