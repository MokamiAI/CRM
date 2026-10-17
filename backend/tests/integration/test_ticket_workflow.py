"""Ticket automation, private files and editable templates against local Postgres."""
import pytest

from app.core.config import settings
from .conftest import new_company


def emails(api, since):
    return [args[0] for name, args in api.queued[since:] if name.endswith("send_platform_email_task")]


@pytest.mark.asyncio
async def test_ticket_files_are_atomic_private_and_downloadable(api, monkeypatch):
    owner = await new_company(api, "Ticket files")
    stranger = await new_company(api, "Other tenant")
    data = {"subject": "Screenshot attached", "body": "Please check this screenshot", "category": "problem", "urgency": "high"}
    before = len(api.queued)
    bad = await api.post("/support/tickets/submit", data=data, files=[("files", ("bad.png", b"not a png", "image/png"))], headers=owner["headers"])
    assert bad.status_code == 422
    assert not emails(api, before)
    assert (await api.get("/support/tickets", headers=owner["headers"])).json() == []
    for files, status in [([("files", ("empty.txt", b"", "text/plain"))], 422),
                          ([("files", ("huge.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain"))], 413),
                          ([("files", (f"{i}.txt", b"ok", "text/plain")) for i in range(6)], 422)]:
        assert (await api.post("/support/tickets/submit", data=data, files=files, headers=owner["headers"])).status_code == status
    result = await api.post("/support/tickets/submit", data=data, files=[("files", ("../notes.txt", b"Reproduction steps", "text/plain"))], headers=owner["headers"])
    assert result.status_code == 201, result.text
    ticket = result.json()
    attachment = ticket["attachments"][0]
    assert attachment["filename"] == "notes.txt" and "data" not in attachment
    path = f"/support/tickets/{ticket['id']}/attachments/{attachment['id']}"
    download = await api.get(path, headers=owner["headers"])
    assert download.content == b"Reproduction steps"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert (await api.get(path, headers=stranger["headers"])).status_code == 404
    assert (await api.get(path)).status_code == 401
    assert (await api.get(path.replace("/support/", "/admin/"), headers=owner["headers"])).status_code == 403
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", stranger["email"])
    assert (await api.get(path.replace("/support/", "/admin/"), headers=stranger["headers"])).content == b"Reproduction steps"
    assert len((await api.get(f"/admin/tickets/{ticket['id']}", headers=stranger["headers"])).json()["attachments"]) == 1


@pytest.mark.asyncio
async def test_every_status_notifies_once_and_internal_notes_stay_private(api, monkeypatch):
    owner = await new_company(api, "Ticket updates")
    admin = await new_company(api, "Support team")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", admin["email"])
    ticket = (await api.post("/support/tickets", json={"subject": "Please investigate", "body": "There is a problem here"}, headers=owner["headers"])).json()
    path = f"/admin/tickets/{ticket['id']}"
    for status in ["in_progress", "waiting", "resolved", "open", "closed"]:
        before = len(api.queued)
        result = await api.patch(path, json={"status": status}, headers=admin["headers"])
        assert result.status_code == 200, result.text
        assert result.json()["status"] == status
        sent = [e for e in emails(api, before) if e["to"] == owner["email"]]
        assert len(sent) == 1 and sent[0]["from_name"] == "YGT Support"
        if status == "waiting":
            assert sent[0]["subject"].startswith("Waiting on client:")
        assert "{" not in result.json()["messages"][-1]["body"]
        before = len(api.queued)
        await api.patch(path, json={"status": status}, headers=admin["headers"])
        assert emails(api, before) == []
    before = len(api.queued)
    await api.post(path + "/messages", json={"body": "Private investigation", "internal": True}, headers=admin["headers"])
    assert emails(api, before) == []
    customer_view = (await api.get(f"/support/tickets/{ticket['id']}", headers=owner["headers"])).json()
    assert not any(m["internal"] or m["body"] == "Private investigation" for m in customer_view["messages"])
    await api.patch(path, json={"status": "resolved"}, headers=admin["headers"])
    reopened = await api.post(f"/support/tickets/{ticket['id']}/messages", json={"body": "Still happening"}, headers=owner["headers"])
    assert reopened.json()["status"] == "open"


@pytest.mark.asyncio
async def test_templates_are_admin_only_and_used_in_emails(api, monkeypatch):
    owner = await new_company(api, "Template tests")
    path = "/admin/ticket-templates"
    assert (await api.get(path, headers=owner["headers"])).status_code == 403
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", owner["email"])
    original = (await api.get(path, headers=owner["headers"])).json()
    edited = [dict(t) for t in original]
    edited[0]["body"] = "Hello {name}, received #{number}: {subject}. Custom acknowledgement."
    try:
        assert (await api.put(path, json=edited, headers=owner["headers"])).status_code == 200
        assert (await api.get(path, headers=owner["headers"])).json() == edited
        assert (await api.put(path, json=edited[:-1], headers=owner["headers"])).status_code == 422
        before = len(api.queued)
        result = await api.post("/support/tickets/submit", data={"subject": "New template", "body": "Check acknowledgement"}, headers=owner["headers"])
        assert result.status_code == 201, result.text
        ack = next(e for e in emails(api, before) if e["to"] == owner["email"])
        assert "Hello Test, received #" in ack["text"] and "Custom acknowledgement" in ack["text"]
    finally:
        await api.put(path, json=original, headers=owner["headers"])
