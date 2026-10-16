"""Files on an activity: attach, list, download, remove. Only business
file types; another company can't see them; they go with the activity."""
import pytest

from .conftest import new_company

PDF = b"%PDF-1.4\n%test\n"


async def _activity(api, owner) -> str:
    res = await api.post("/activities", json={"type": "task", "subject": "Send the signed quote", "due_date": "2026-10-20"}, headers=owner["headers"])
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.mark.asyncio
async def test_attach_download_remove(api):
    owner = await new_company(api, "Files Co")
    aid = await _activity(api, owner)
    res = await api.post(f"/activities/{aid}/attachments", files={"file": ("../Signed quote.pdf", PDF, "application/pdf")}, headers=owner["headers"])
    assert res.status_code == 201, res.text
    att = res.json()
    assert att["filename"] == "Signed quote.pdf" and att["size"] == len(PDF) and att["content_type"] == "application/pdf"

    listed = (await api.get(f"/activities/{aid}/attachments", headers=owner["headers"])).json()
    assert [a["id"] for a in listed] == [att["id"]]

    dl = await api.get(f"/activities/{aid}/attachments/{att['id']}", headers=owner["headers"])
    assert dl.status_code == 200 and dl.content == PDF
    assert dl.headers["content-disposition"].startswith("attachment;") and dl.headers["x-content-type-options"] == "nosniff"

    # Another company can't list or open it.
    other = await new_company(api, "Nosy Co")
    assert (await api.get(f"/activities/{aid}/attachments", headers=other["headers"])).status_code == 404
    assert (await api.get(f"/activities/{aid}/attachments/{att['id']}", headers=other["headers"])).status_code == 404

    assert (await api.delete(f"/activities/{aid}/attachments/{att['id']}", headers=owner["headers"])).status_code == 204
    assert (await api.get(f"/activities/{aid}/attachments", headers=owner["headers"])).json() == []


@pytest.mark.asyncio
async def test_refuses_risky_or_fake_files(api):
    owner = await new_company(api, "Careful Co")
    aid = await _activity(api, owner)
    for name, body in [("page.html", b"<script>alert(1)</script>"), ("logo.svg", b"<svg/>"), ("tool.exe", b"MZ..."), ("fake.pdf", b"<html>")]:
        res = await api.post(f"/activities/{aid}/attachments", files={"file": (name, body, "application/octet-stream")}, headers=owner["headers"])
        assert res.status_code == 422 and res.json()["error_code"] == "ATTACHMENT_BAD_TYPE", (name, res.text)
    ok = await api.post(f"/activities/{aid}/attachments", files={"file": ("list.csv", b"a,b\n1,2\n", "text/csv")}, headers=owner["headers"])
    assert ok.status_code == 201
    # Deleting the activity takes its files with it.
    assert (await api.delete(f"/activities/{aid}", headers=owner["headers"])).status_code == 204
    assert (await api.get(f"/activities/{aid}/attachments", headers=owner["headers"])).status_code == 404
