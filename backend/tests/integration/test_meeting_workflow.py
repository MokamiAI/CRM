import asyncio
import re
import pytest

from app.core.config import settings
from .conftest import new_company


@pytest.fixture(autouse=True)
def configured_mail(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "local-capture.invalid")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "calendar@example.com")


async def setup(api, *, email="buyer@example.com"):
    owner = await new_company(api, "Meeting workflow")
    headers = owner["headers"]
    prospect = (await api.post("/prospects", headers=headers, json={
        "name": "Meeting prospect", "contact": {"name": "Lerato Buyer", "email": email}
    })).json()
    contacts = (await api.get(f"/customers/{prospect['id']}/contacts", headers=headers)).json()
    deal = (await api.post("/deals", headers=headers, json={"title": "Meeting opportunity", "customer_id": prospect["id"], "contact_id": contacts[0]["id"]})).json()
    return owner, deal


async def invite(api, owner, deal=None, *, at="10:00", day="2030-05-14", **options):
    return await api.post("/activities", headers=owner["headers"], json={
        "type": "meeting", "subject": "Discuss requirements", "due_date": day, "due_time": at,
        **({"deal_id": deal["id"]} if deal else {}),
        "meeting": {"attendee_name": "Independent Guest", "attendee_email": "standalone@example.com", "duration_minutes": 45, **options},
    })


def emails(api):
    return [args[1] for name, args in api.queued if name.endswith("send_meeting_email_task")]


def link(api):
    email = next(email for email in reversed(emails(api)) if "Respond in YGT" in email["text"])
    return re.search(r"/public/meetings/([A-Za-z0-9_.-]+)", email["text"]).group(0)


async def calendar(api, owner):
    response = await api.get("/meetings/calendar?start=2030-05-01&end=2030-06-01", headers=owner["headers"])
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_pipeline_contact_invite_calendar_acceptance_and_scanner_safety(api):
    owner, deal = await setup(api)
    res = await invite(api, owner, deal)
    assert res.status_code == 201, res.text
    activity = res.json()
    assert activity["meeting"]["attendee_email"] == "buyer@example.com"
    assert activity["meeting"]["attendee_name"] == "Lerato Buyer"
    assert {email["to"] for email in emails(api)} == {"buyer@example.com", owner["email"]}
    assert len(await calendar(api, owner)) == 1
    path = link(api)
    assert (await api.get(path)).status_code == 200
    assert (await api.get(f"/activities/{activity['id']}", headers=owner["headers"])).json()["meeting"]["status"] == "invited"
    ics = await api.get(path + "/calendar.ics")
    assert "STATUS:TENTATIVE" in ics.text and "TRANSP:OPAQUE" in ics.text
    accepted = await api.post(path, data={"action": "accept"})
    assert accepted.status_code == 200, accepted.text
    before = len(emails(api))
    assert (await api.post(path, data={"action": "accept"})).status_code == 200
    assert len(emails(api)) == before
    assert (await calendar(api, owner))[0]["status"] == "accepted"
    assert "STATUS:CONFIRMED" in (await api.get(path + "/calendar.ics")).text
    history = (await api.get(f"/deals/{deal['id']}/timeline", headers=owner["headers"])).json()
    assert any("meeting accepted" in (item.get("detail") or "") for item in history)


@pytest.mark.asyncio
async def test_missing_details_prompt_and_save_contact_email(api):
    owner, deal = await setup(api, email=None)
    contact = (await api.get(f"/meetings/contact?deal_id={deal['id']}", headers=owner["headers"])).json()
    assert contact["name"] == "Lerato Buyer" and not contact["email"]
    missing = await invite(api, owner, deal, attendee_email=None)
    assert missing.status_code == 409, missing.text
    assert not (await api.get("/activities", headers=owner["headers"])).json()
    good = await invite(api, owner, deal, attendee_email="filled@example.com")
    assert good.status_code == 201, good.text
    assert (await api.get(f"/meetings/contact?deal_id={deal['id']}", headers=owner["headers"])).json()["email"] == "filled@example.com"
    other = await new_company(api, "Standalone meeting")
    missing = await invite(api, other, attendee_email=None, attendee_name=None)
    assert missing.status_code == 409


@pytest.mark.asyncio
async def test_decline_needs_reason_and_releases_calendar(api):
    owner, deal = await setup(api)
    response = await invite(api, owner, deal)
    assert response.status_code == 201, response.text
    path = link(api)
    assert (await api.post(path, data={"action": "decline"})).status_code == 409
    declined = await api.post(path, data={"action": "decline", "reason": "I am unavailable <script>alert(1)</script>"})
    assert declined.status_code == 200, declined.text
    assert "<script>" not in declined.text and "&lt;script&gt;" in declined.text
    assert await calendar(api, owner) == []
    assert any(email["calendar_method"] == "CANCEL" for email in emails(api))


@pytest.mark.asyncio
async def test_proposed_time_holds_both_slots_until_organizer_decides(api):
    owner, deal = await setup(api)
    activity = (await invite(api, owner, deal)).json()
    old_link = link(api)
    proposed = await api.post(old_link, data={"action": "propose", "proposed_start": "2030-05-15T14:00", "reason": "A better time"})
    assert proposed.status_code == 200, proposed.text
    holds = await calendar(api, owner)
    assert len(holds) == 2 and sum(hold["proposed"] for hold in holds) == 1
    busy = await invite(api, owner, at="14:15", day="2030-05-15")
    assert busy.status_code == 409, busy.text
    approved = await api.post(f"/meetings/{activity['id']}/proposal", headers=owner["headers"], json={"accept": True})
    assert approved.status_code == 200, approved.text
    holds = await calendar(api, owner)
    assert len(holds) == 1 and holds[0]["status"] == "accepted"
    assert (await api.get(f"/activities/{activity['id']}", headers=owner["headers"])).json()["due_date"] == "2030-05-15"
    assert (await api.get(old_link)).status_code == 401
    assert any("-proposal-0@" in email["calendar"] and email["calendar_method"] == "CANCEL" for email in emails(api))
    cancelled = await api.post(f"/meetings/{activity['id']}/cancel", headers=owner["headers"])
    assert cancelled.status_code == 200 and not await calendar(api, owner)


@pytest.mark.asyncio
async def test_reject_proposal_and_revise_invalidates_old_links(api):
    owner, deal = await setup(api)
    activity = (await invite(api, owner, deal)).json()
    old = link(api)
    assert (await api.post(old, data={"action": "propose", "proposed_start": "2030-05-16T11:00"})).status_code == 200
    res = await api.post(f"/meetings/{activity['id']}/proposal", headers=owner["headers"], json={"accept": False, "reason": "Original time preferred"})
    assert res.status_code == 200, res.text
    assert len(await calendar(api, owner)) == 1
    assert (await api.post(old, data={"action": "accept"})).status_code == 401
    current = link(api)
    assert (await api.get(current)).status_code == 200
    edited = await api.patch(f"/activities/{activity['id']}", headers=owner["headers"], json={"due_time": "12:00"})
    assert edited.status_code == 200, edited.text
    assert (await api.get(current)).status_code == 401
    other = await new_company(api, "Private calendar")
    assert (await api.get("/meetings/calendar?start=2030-05-01&end=2030-06-01&mine=false", headers=other["headers"])).json() == []
    assert (await api.post(f"/meetings/{activity['id']}/cancel", headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_concurrent_meetings_cannot_double_book_one_calendar(api):
    owner, deal = await setup(api)
    first, second = await asyncio.gather(invite(api, owner, deal), invite(api, owner, attendee_email="another@example.com"))
    assert sorted([first.status_code, second.status_code]) == [201, 409], (first.text, second.text)
    assert len(await calendar(api, owner)) == 1


@pytest.mark.asyncio
async def test_missing_mail_configuration_cannot_create_a_false_invitation(api, monkeypatch):
    owner, deal = await setup(api)
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    response = await invite(api, owner, deal)
    assert response.status_code == 400, response.text
    assert not emails(api)
    assert not (await api.get("/activities", headers=owner["headers"])).json()


@pytest.mark.asyncio
async def test_signed_response_requires_meeting_credential_and_valid_proposal(api):
    owner, deal = await setup(api)
    activity = (await invite(api, owner, deal)).json()
    path = link(api)
    credential = owner["headers"]["Authorization"].removeprefix("Bearer ")
    wrong_purpose = await api.get(f"/public/meetings/{credential}")
    assert wrong_purpose.status_code == 401
    assert "Use the latest invitation" in wrong_purpose.text
    tampered = await api.post(path + "changed", data={"action": "accept"})
    assert tampered.status_code == 401
    invalid = await api.post(path, data={"action": "propose", "proposed_start": "2000-01-01T10:00"})
    assert invalid.status_code == 409 and "future date and time" in invalid.text
    assert "role=\"alert\"" in invalid.text
    saved = (await api.get(f"/activities/{activity['id']}", headers=owner["headers"])).json()
    assert saved["meeting"]["status"] == "invited" and len(await calendar(api, owner)) == 1
    proposal = await api.post(path, data={"action": "propose", "proposed_start": "2030-05-15T14:00"})
    assert proposal.status_code == 200 and "calendar.ics?proposed=true" in proposal.text
    calendar_file = await api.get(path + "/calendar.ics?proposed=true")
    assert "DTSTART:20300515T120000Z" in calendar_file.text
    assert "-proposal-0@yougt.co.za" in calendar_file.text.replace("\r\n ", "")
