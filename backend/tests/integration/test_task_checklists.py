import asyncio
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.models.crm import Activity
from app.tasks.notification_tasks import remind_company
from .conftest import new_company
from .test_team_tasks import _member


async def task(api, headers, **overrides):
    response = await api.post("/activities", headers=headers, json={
        "subject": "Shared checklist", "due_date": date.today().isoformat(), "checklist_enabled": True, **overrides
    })
    assert response.status_code == 201, response.text
    return response.json()


async def add(api, headers, activity, title):
    response = await api.post(f"/activities/{activity['id']}/checklist", headers=headers, json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_progress_stages_manual_block_and_reopen(api):
    owner = await new_company(api, "Checklist Stages")
    headers = owner["headers"]
    activity = await task(api, headers)
    assert activity["completion_percentage"] == 0 and activity["done"] is False
    activity = await add(api, headers, activity, "Prepare quote")
    activity = await add(api, headers, activity, "Review quote")
    base = f"/activities/{activity['id']}"
    first, second = activity["checklist"]
    early = await api.patch(base, headers=headers, json={"done": True})
    assert early.status_code == 409
    result = await api.patch(f"{base}/checklist/{first['id']}", headers=headers, json={"done": True})
    assert result.json()["completion_percentage"] == 50 and result.json()["status"] == "in_progress"
    assert result.json()["checklist"][0]["completed_by"] == str(owner["user_id"])
    blocked = await api.post(base + "/updates", headers=headers, json={"status": "blocked", "note": "Waiting for approval"})
    assert blocked.status_code == 201
    partial = await api.patch(f"{base}/checklist/{first['id']}", headers=headers, json={"done": False})
    assert partial.json()["status"] == "blocked"
    await api.patch(f"{base}/checklist/{first['id']}", headers=headers, json={"done": True})
    complete = await api.patch(f"{base}/checklist/{second['id']}", headers=headers, json={"done": True})
    assert complete.json()["status"] == "done" and complete.json()["done_at"] and complete.json()["completion_percentage"] == 100
    reopened = await api.patch(f"{base}/checklist/{first['id']}", headers=headers, json={"done": False})
    assert reopened.json()["status"] == "in_progress" and reopened.json()["done"] is False
    disabled = await api.patch(base, headers=headers, json={"checklist_enabled": False})
    assert disabled.json()["completion_percentage"] is None and len(disabled.json()["checklist"]) == 2
    assert (await api.post(base + "/updates", headers=headers, json={"status": "todo"})).status_code == 201
    assert (await api.patch(base, headers=headers, json={"checklist_enabled": True})).json()["completion_percentage"] == 50
    assert len((await api.get(base + "/updates", headers=headers)).json()) >= 7


@pytest.mark.asyncio
async def test_multiple_assignees_see_tasks_and_cannot_cross_workspaces(api):
    owner = await new_company(api, "Shared Assignment")
    staff, staff_id = await _member(api, owner)
    viewer, viewer_id = await _member(api, owner, "viewer")
    team = (await api.get("/team", headers=staff)).json()
    assert next(person for person in team if person["id"] == viewer_id)["can_receive_tasks"] is False
    activity = await task(api, owner["headers"], assignee_ids=[staff_id, staff_id])
    assert activity["assignee_ids"] == [staff_id]
    mine = (await api.get("/activities?mine=true", headers=staff)).json()
    assert any(item["id"] == activity["id"] for item in mine)
    assert sum((await api.get("/activities/counts", headers=staff)).json().values()) >= 1
    assert any(n["kind"] == "task_assigned" for n in (await api.get("/notifications", headers=staff)).json()["items"])
    other = await new_company(api, "Foreign Assignee")
    base = f"/activities/{activity['id']}"
    for invalid in (str(other["user_id"]), viewer_id):
        response = await api.patch(base, headers=owner["headers"], json={"assignee_ids": [invalid]})
        assert response.status_code == 409
    activity = await add(api, staff, activity, "Assigned colleague's subtask")
    assert (await api.post(base + "/checklist", headers=viewer, json={"title": "Forbidden"})).status_code == 403
    assert (await api.get(base, headers=other["headers"])).status_code == 404
    item_id = activity["checklist"][0]["id"]
    assert (await api.patch(base + f"/checklist/{item_id}", headers=other["headers"], json={"done": True})).status_code == 404
    other_task = await task(api, owner["headers"])
    assert (await api.patch(f"/activities/{other_task['id']}/checklist/{item_id}", headers=staff, json={"done": True})).status_code == 404


@pytest.mark.asyncio
async def test_two_people_ticking_different_items_do_not_lose_changes(api):
    owner = await new_company(api, "Concurrent Checklists")
    staff, staff_id = await _member(api, owner)
    activity = await task(api, owner["headers"], assignee_ids=[staff_id])
    activity = await add(api, owner["headers"], activity, "First")
    activity = await add(api, owner["headers"], activity, "Second")
    results = await asyncio.gather(*[
        api.patch(f"/activities/{activity['id']}/checklist/{item['id']}", headers=headers, json={"done": True})
        for item, headers in zip(activity["checklist"], [owner["headers"], staff])
    ])
    assert all(result.status_code == 200 for result in results)
    updated = (await api.get(f"/activities/{activity['id']}", headers=owner["headers"])).json()
    assert all(item["done"] for item in updated["checklist"]) and updated["completion_percentage"] == 100


@pytest.mark.asyncio
async def test_daily_digest_and_two_hour_reminders_are_deduplicated_for_every_assignee(api):
    owner = await new_company(api, "Task Reminder Digest")
    staff, staff_id = await _member(api, owner)
    tz = ZoneInfo("Africa/Johannesburg")
    today = date(2027, 2, 2)  # Tuesday: avoids the weekly pipeline reminder.
    tasks = []
    for title in ("Prepare", "Review"):
        tasks.append(await task(api, owner["headers"], subject=title, due_date=today.isoformat(), due_time="14:00", assignee_ids=[staff_id], checklist_enabled=False))
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        await db.execute(update(Activity).where(Activity.id.in_([uuid.UUID(item["id"]) for item in tasks])).values(
            created_at=datetime.combine(today - timedelta(days=1), time(9), tz)))
        await db.commit()
    assert await remind_company(owner["company_id"], datetime.combine(today, time(9), tz)) == 2  # one digest per person
    assert await remind_company(owner["company_id"], datetime.combine(today, time(9, 1), tz)) == 0
    assert await remind_company(owner["company_id"], datetime.combine(today, time(11, 59), tz)) == 0
    assert await remind_company(owner["company_id"], datetime.combine(today, time(12), tz)) == 4  # two deadlines x two people
    assert await remind_company(owner["company_id"], datetime.combine(today, time(12, 1), tz)) == 0
    for headers in (owner["headers"], staff):
        notes = (await api.get("/notifications", headers=headers)).json()["items"]
        digests = [note for note in notes if note["kind"] == "task_digest"]
        assert len(digests) == 1 and "Prepare" in digests[0]["body"] and "Review" in digests[0]["body"]
        assert len([note for note in notes if note["kind"] == "task_deadline"]) == 2
    for item in tasks:
        await api.patch(f"/activities/{item['id']}", headers=owner["headers"], json={"done": True})
    assert await remind_company(owner["company_id"], datetime.combine(today + timedelta(days=1), time(9), tz)) == 0


@pytest.mark.asyncio
async def test_deadline_reminder_crosses_midnight_and_respects_opt_out(api):
    owner = await new_company(api, "Midnight Task Reminder")
    tz = ZoneInfo("Africa/Johannesburg")
    today = date(2027, 2, 2)
    for enabled in (True, False):
        await task(api, owner["headers"], subject=f"Midnight {enabled}",
                   due_date=(today + timedelta(days=1)).isoformat(), due_time="01:00",
                   daily_reminders=False, deadline_reminders=enabled, checklist_enabled=False)
    assert await remind_company(owner["company_id"], datetime.combine(today, time(22, 59), tz)) == 0
    assert await remind_company(owner["company_id"], datetime.combine(today, time(23), tz)) == 1
    assert await remind_company(owner["company_id"], datetime.combine(today, time(23, 1), tz)) == 0
    notes = (await api.get("/notifications", headers=owner["headers"])).json()["items"]
    assert len([note for note in notes if note["kind"] == "task_deadline"]) == 1
