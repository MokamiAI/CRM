import pytest

from .conftest import new_company
from .test_team_tasks import _member
from app.core.config import settings
from app.services.reminder_service import company_today


def _today():
    # "Today" as the company sees it (Johannesburg), not the server's UTC date.
    return company_today("Africa/Johannesburg").isoformat()


@pytest.mark.asyncio
async def test_staff_and_viewer_cannot_read_other_peoples_tasks_through_any_route(api):
    admin = await new_company(api, "Task privacy")
    staff, staff_id = await _member(api, admin)
    viewer, _ = await _member(api, admin, "viewer")
    prospect = (await api.post("/prospects", headers=admin["headers"], json={"name": "Private tasks prospect"})).json()
    deal = (await api.post("/deals", headers=admin["headers"], json={"title": "Task privacy deal", "customer_id": prospect["id"]})).json()
    private = (await api.post("/activities", headers=admin["headers"], json={
        "subject": "Admin private task", "due_date": _today(), "deal_id": deal["id"], "checklist_enabled": True,
    })).json()
    attachment = await api.post(f"/activities/{private['id']}/attachments", headers=admin["headers"], files={"file": ("private.txt", b"private notes", "text/plain")})
    assert attachment.status_code == 201, attachment.text
    attachment_id = attachment.json()["id"]
    assert (await api.post(f"/activities/{private['id']}/updates", headers=admin["headers"], json={"status": "done", "note": "Private update"})).status_code == 201
    mine = (await api.post("/activities", headers=admin["headers"], json={"subject": "Assigned to staff", "due_date": _today(), "owner_id": staff_id})).json()
    shared = (await api.post("/activities", headers=admin["headers"], json={"subject": "Shared with staff", "due_date": _today(), "assignee_ids": [staff_id]})).json()
    created = (await api.post("/activities", headers=staff, json={"subject": "Created by staff", "due_date": _today(), "owner_id": str(admin["user_id"])})).json()
    visible_ids = {mine["id"], shared["id"], created["id"]}
    for query in ["", "?mine=false", f"?deal_id={deal['id']}", f"?customer_id={prospect['id']}"]:
        response = await api.get("/activities" + query, headers=staff)
        assert response.status_code == 200, response.text
        assert private["id"] not in {task["id"] for task in response.json()}
    assert {task["id"] for task in (await api.get("/activities", headers=staff)).json()} == visible_ids
    assert (await api.get("/activities/counts?mine=false", headers=staff)).json()["today"] == 3
    assert not (await api.get("/activities", headers=viewer)).json()
    for headers in [staff, viewer]:
        for suffix in ["", "/updates", "/attachments", f"/attachments/{attachment_id}"]:
            assert (await api.get(f"/activities/{private['id']}" + suffix, headers=headers)).status_code == 404
        for url in [f"/deals/{deal['id']}/timeline", f"/customers/{prospect['id']}/timeline"]:
            timeline = await api.get(url, headers=headers)
            assert timeline.status_code == 200, timeline.text
            assert private["id"] not in {item.get("ref_id") for item in timeline.json()}
        assert (await api.get("/meetings/calendar?start=2030-01-01&end=2030-01-08&mine=false", headers=headers)).status_code == 403
    assert (await api.patch(f"/activities/{private['id']}", headers=staff, json={"subject": "Changed"})).status_code == 404
    assert (await api.post(f"/activities/{private['id']}/checklist", headers=staff, json={"title": "Try edit"})).status_code == 404
    assert (await api.delete(f"/activities/{private['id']}/attachments/{attachment_id}", headers=staff)).status_code == 404


@pytest.mark.asyncio
async def test_admin_and_manager_keep_everyone_visibility_and_shared_tasks_work(api):
    admin = await new_company(api, "Manager task overview")
    manager, _ = await _member(api, admin, "manager")
    staff, staff_id = await _member(api, admin)
    task = (await api.post("/activities", headers=admin["headers"], json={"subject": "Team task", "due_date": _today(), "assignee_ids": [staff_id], "checklist_enabled": True})).json()
    for headers in [admin["headers"], manager, staff]:
        assert task["id"] in {row["id"] for row in (await api.get("/activities?mine=false", headers=headers)).json()}
        assert (await api.get(f"/activities/{task['id']}", headers=headers)).status_code == 200
    assert (await api.post(f"/activities/{task['id']}/checklist", headers=staff, json={"title": "Shared work"})).status_code == 201
    for headers in [admin["headers"], manager]:
        assert (await api.get("/meetings/calendar?start=2030-01-01&end=2030-01-08&mine=false", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_hidden_meetings_still_block_double_booking_without_exposing_details(api, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "local-capture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "calendar@example.com")
    admin = await new_company(api, "Private calendar conflicts")
    staff, _ = await _member(api, admin)
    draft = {"type": "meeting", "subject": "Private admin meeting", "due_date": "2030-07-01", "due_time": "10:00",
             "meeting": {"attendee_name": "Shared guest", "attendee_email": "shared-guest@example.com", "duration_minutes": 60}}
    response = await api.post("/activities", headers=admin["headers"], json=draft)
    assert response.status_code == 201, response.text
    activity_id = response.json()["id"]
    assert (await api.get(f"/meetings/{activity_id}/calendar.ics", headers=staff)).status_code == 404
    assert not (await api.get("/meetings/calendar?start=2030-07-01&end=2030-07-08", headers=staff)).json()
    conflict = await api.post("/activities", headers=staff, json={**draft, "subject": "My overlapping meeting"})
    assert conflict.status_code == 409, conflict.text
    assert "Private admin meeting" not in conflict.text
