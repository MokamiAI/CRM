"""Activity progress and quoted prices stay consistent across CRM screens."""
from datetime import date
from decimal import Decimal

import pytest

from .conftest import new_company


async def workspace(api, name):
    owner = await new_company(api, name)
    headers = owner["headers"]
    account = (await api.post("/prospects", headers=headers, json={"name": name + " prospect"})).json()
    deal = (await api.post("/deals", headers=headers, json={
        "title": name + " sale", "customer_id": account["id"], "value": "500"
    })).json()
    return headers, account, deal


@pytest.mark.asyncio
async def test_activity_updates_reach_queue_and_both_workspace_histories(api):
    headers, account, deal = await workspace(api, "Activity Sync")
    res = await api.post("/activities", headers=headers, json={
        "type": "call", "subject": "Confirm requirements", "deal_id": deal["id"],
        "due_date": date.today().isoformat(),
    })
    assert res.status_code == 201, res.text
    activity = res.json()
    assert activity["customer_id"] == account["id"]
    update = await api.post(f"/activities/{activity['id']}/updates", headers=headers,
                            json={"status": "in_progress", "note": "Contact reached from the queue"})
    assert update.status_code == 201, update.text
    for path in (f"/deals/{deal['id']}/timeline", f"/customers/{account['id']}/timeline"):
        history = (await api.get(path, headers=headers)).json()
        assert any(item["kind"] == "activity_update" and item["detail"] == "Contact reached from the queue" for item in history)
    queued = (await api.get("/activities", headers=headers, params={"deal_id": deal["id"]})).json()
    assert queued[0]["status"] == "in_progress"
    # The workspace edits the same record; the main queue sees it too.
    result = await api.patch(f"/activities/{activity['id']}", headers=headers, json={"subject": "Confirmed requirements"})
    assert result.status_code == 200
    result = await api.post(f"/activities/{activity['id']}/updates", headers=headers,
                            json={"status": "done", "note": "Requirements confirmed in the workspace"})
    assert result.status_code == 201, result.text
    done = (await api.get("/activities", headers=headers, params={"scope": "done"})).json()
    assert any(item["id"] == activity["id"] and item["subject"] == "Confirmed requirements" for item in done)
    assert (await api.get(f"/activities/{activity['id']}", headers=headers)).json()["done"] is True
    other = await new_company(api, "Unrelated Workspace")
    assert (await api.get(f"/activities/{activity['id']}", headers=other["headers"])).status_code == 404
    assert (await api.get(f"/activities/{activity['id']}/updates", headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_unlinked_task_can_be_completed_and_undone_without_creating_workspace(api):
    owner = await new_company(api, "Standalone Activity")
    headers = owner["headers"]
    activity = (await api.post("/activities", headers=headers, json={
        "subject": "Organise desk", "due_date": date.today().isoformat()
    })).json()
    assert activity["deal_id"] is None and activity["customer_id"] is None
    for done in (True, False):
        result = await api.patch(f"/activities/{activity['id']}", headers=headers, json={"done": done})
        assert result.status_code == 200, result.text
        assert result.json()["done"] is done
        assert result.json()["status"] == ("done" if done else "todo")


@pytest.mark.asyncio
async def test_quote_price_synchronizes_only_its_linked_pipeline(api):
    headers, account, deal = await workspace(api, "Quote Price Sync")
    unrelated = (await api.post("/deals", headers=headers, json={
        "title": "Separate opportunity", "customer_id": account["id"], "value": "321"
    })).json()
    line = {"description": "Service", "quantity": "2", "unit_price": "100", "tax_rate": "15"}
    quote = await api.post("/quotes", headers=headers, json={
        "customer_id": account["id"], "deal_id": deal["id"],
        "issue_date": date.today().isoformat(), "items": [line]
    })
    assert quote.status_code == 201, quote.text
    quote = quote.json()
    assert Decimal((await api.get(f"/deals/{deal['id']}", headers=headers)).json()["value"]) == Decimal("230")
    revised = await api.patch(f"/quotes/{quote['id']}", headers=headers,
                              json={"items": [line | {"unit_price": "250.50"}]})
    assert revised.status_code == 200, revised.text
    pipeline = (await api.get(f"/deals/{deal['id']}", headers=headers)).json()
    assert Decimal(pipeline["value"]) == Decimal(revised.json()["total"]) == Decimal("576.15")
    assert Decimal((await api.get(f"/deals/{unrelated['id']}", headers=headers)).json()["value"]) == Decimal("321")
    # Notes-only edits don't overwrite a later intentional value change.
    await api.patch(f"/deals/{deal['id']}", headers=headers, json={"value": "600"})
    await api.patch(f"/quotes/{quote['id']}", headers=headers, json={"notes": "New delivery details"})
    assert Decimal((await api.get(f"/deals/{deal['id']}", headers=headers)).json()["value"]) == Decimal("600")


@pytest.mark.asyncio
async def test_booking_invites_go_to_johannes_and_include_personal_signature(api, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BOOKING_CALENDAR_EMAIL", "johannes@yougt.co.za")
    monkeypatch.setattr(settings, "BOOKING_HOST_NAME", "Johannes")
    owner = await new_company(api, "Founder Call")
    headers = owner["headers"]
    slots = (await api.get("/bookings/slots", headers=headers)).json()
    assert slots["host_name"] == "Johannes" and slots["host_email"] == "johannes@yougt.co.za"
    assert slots["days"]
    before = len(api.queued)
    booking = await api.post("/bookings", headers=headers, json={
        "starts_at": slots["days"][0]["slots"][0], "topic": "onboarding", "notes": "Show me the activity workspace"
    })
    assert booking.status_code == 201, booking.text
    emails = [args[0] for name, args in api.queued[before:] if name.endswith("send_platform_email_task")]
    assert {email["to"] for email in emails} == {owner["email"], "johannes@yougt.co.za"}
    attendee = next(email for email in emails if email["to"] == owner["email"])
    assert attendee["headers"]["Reply-To"] == "johannes@yougt.co.za"
    assert "Kind regards,\nJohannes\nFounder | YGT" in attendee["text"]
    assert "mailto:johannes@yougt.co.za" in attendee["calendar"]
    assert "METHOD:REQUEST" in attendee["calendar"]
    again = await api.post("/bookings", headers=headers, json={"starts_at": slots["days"][0]["slots"][0]})
    assert again.status_code == 409
    before = len(api.queued)
    cancelled = await api.post(f"/bookings/{booking.json()['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    cancellations = [args[0] for name, args in api.queued[before:] if name.endswith("send_platform_email_task")]
    assert len(cancellations) == 2
    assert all("METHOD:CANCEL" in email["calendar"] for email in cancellations)
