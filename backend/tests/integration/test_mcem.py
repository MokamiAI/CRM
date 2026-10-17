"""The procurement journey, stage gates, history, tenancy and reminders."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system, set_tenant
from app.models.enums import UserRole
from app.models.mcem import McemJourney
from app.models.user import User
from app.services.mcem_service import McemService
from .conftest import new_company

TODAY = datetime.now(ZoneInfo("Africa/Johannesburg")).date()


async def setup(api, enabled=True):
    owner = await new_company(api, "MCEM procurement")
    h = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Procurement Customer"}, headers=h)).json()
    person = (await api.post(f"/customers/{customer['id']}/contacts", json={"first_name": "Lerato", "email": "lerato@example.com"}, headers=h)).json()
    result = await api.post("/deals", json={"title": "Tender preparation workflow", "customer_id": customer["id"], "contact_id": person["id"], "value": "25000", "mcem_enabled": enabled}, headers=h)
    assert result.status_code == 201, result.text
    deal = result.json()
    note = (await api.post("/notes", json={"body": "Customer workshop: the agreed requirements and signed order are recorded here.", "deal_id": deal["id"]}, headers=h)).json()
    return owner, customer, person, deal, note


async def confirm(api, owner, deal, note, key, summary="Customer confirmed this milestone at the workshop"):
    path = f"/deals/{deal['id']}/mcem/milestones/{key}"
    result = await api.post(path + "/evidence", json={"kind": "note", "ref_id": note["id"], "explanation": summary, "occurred_on": str(TODAY)}, headers=owner["headers"])
    assert result.status_code == 201, result.text
    result = await api.patch(path, json={"status": "confirmed", "confirmed_on": str(TODAY), "summary": summary}, headers=owner["headers"])
    assert result.status_code == 200, result.text
    return result.json()


async def prepare(api, owner, deal):
    result = await api.patch(f"/deals/{deal['id']}/mcem/journey", json={
        "qualification_reason": "Their manual tender preparation fits our workflow solution",
        "decision_process": "Procurement director approves after the workshop",
        "scope": "Tender preparation workflow and team training", "commitments": "Deliver the workflow and train five users",
        "success_measure": "Hours spent preparing each tender", "baseline": "12", "target": "4", "unit": "hours per tender",
        "next_review_date": str(TODAY + timedelta(days=7)),
    }, headers=owner["headers"])
    assert result.status_code == 200, result.text
    result = await api.post("/activities", json={"subject": "Review the proposed workflow with Lerato", "type": "meeting", "due_date": str(TODAY + timedelta(days=1)), "deal_id": deal["id"]}, headers=owner["headers"])
    assert result.status_code == 201, result.text


@pytest.mark.asyncio
async def test_procurement_sale_to_value_and_separate_expansion(api):
    owner, customer, person, deal, note = await setup(api)
    h = owner["headers"]
    path = f"/deals/{deal['id']}"
    data = (await api.get(path + "/mcem", headers=h)).json()
    assert len(data["milestones"]) == 13
    assert all(m["status"] == "not_started" for m in data["milestones"])
    assert (await api.patch(path, json={"stage": "won"}, headers=h)).status_code == 409
    assert (await api.patch(path + "/mcem/milestones/fit", json={"status": "confirmed", "confirmed_on": str(TODAY)}, headers=h)).status_code == 409
    await prepare(api, owner, deal)
    for stage, keys in [("qualified", ["fit"]), ("proposal", ["problem", "outcome", "solution"]), ("negotiation", ["validation", "proposal_review"]), ("won", ["agreement"])]:
        for key in keys:
            await confirm(api, owner, deal, note, key)
        result = await api.patch(path, json={"stage": stage}, headers=h)
        assert result.status_code == 200, result.text
    journey = (await api.get(path + "/mcem", headers=h)).json()
    assert journey["journey"]["state"] == "active" and journey["phase"] == "Realize Value"
    assert (await api.post(path + "/mcem/enable", headers=h)).json()["journey"]["id"] == journey["journey"]["id"]
    assert (await api.patch(path, json={"stage": "won"}, headers=h)).status_code == 200
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        assert len(list(await db.scalars(select(McemJourney)))) == 1
    # Numerical success measures need an actual result as well as the review.
    await confirm(api, owner, deal, note, "delivery")
    await confirm(api, owner, deal, note, "adoption")
    await api.post(path + "/mcem/milestones/value/evidence", json={"kind": "note", "ref_id": note["id"], "explanation": "Customer reviewed time savings", "occurred_on": str(TODAY)}, headers=h)
    assert (await api.patch(path + "/mcem/milestones/value", json={"status": "confirmed", "confirmed_on": str(TODAY), "summary": "Measured and reviewed"}, headers=h)).status_code == 409
    await api.patch(path + "/mcem/journey", json={"actual": "5"}, headers=h)
    result = await api.patch(path + "/mcem/milestones/value", json={"status": "confirmed", "confirmed_on": str(TODAY), "summary": "Now five hours; one hour above target. Train two additional users."}, headers=h)
    assert result.status_code == 200, result.text
    assert result.json()["phase"] == "Manage and Optimize"
    pipeline = (await api.get("/mcem/report", headers=h)).json()["opportunities"]
    assert next(row for row in pipeline if row["id"] == deal["id"])["phase"] == "Manage and Optimize"
    await api.patch(path + "/mcem/journey", json={"next_review_date": str(TODAY), "recurring": True, "renewal_date": str(TODAY)}, headers=h)
    assert (await api.get("/mcem/report", headers=h)).json()["reviews_due"] == 1
    await confirm(api, owner, deal, note, "health")
    await confirm(api, owner, deal, note, "renewal")
    reviewed = (await api.get("/mcem/report", headers=h)).json()
    assert reviewed["reviews_due"] == 0 and reviewed["renewals_due"] == 0
    scheduled = await api.patch(path + "/mcem/journey", json={"next_review_date": str(TODAY + timedelta(days=30))}, headers=h)
    assert next(m for m in scheduled.json()["milestones"] if m["key"] == "health")["needs_review"]
    expanded = await api.post(path + "/mcem/expansions", json={"title": "Supplier onboarding workflow", "value": "5000"}, headers=h)
    assert expanded.status_code == 201, expanded.text
    child = (await api.get("/deals/" + expanded.json()["id"], headers=h)).json()
    assert child["stage"] == "lead" and child["parent_deal_id"] == deal["id"] and child["mcem_enabled"]
    assert (await api.get(path, headers=h)).json()["stage"] == "won"
    assert all(d["id"] != deal["id"] for d in (await api.get("/deals?status=open", headers=h)).json())
    timeline = (await api.get(path + "/timeline", headers=h)).json()
    assert any(item["kind"] == "mcem" for item in timeline)
    history = (await api.get(path + "/mcem/history?limit=2", headers=h)).json()
    older = (await api.get(path + "/mcem/history?offset=2&limit=2", headers=h)).json()
    assert len(history) == len(older) == 2 and {e["id"] for e in history}.isdisjoint(e["id"] for e in older)
    customer_timeline = (await api.get(f"/customers/{customer['id']}/timeline", headers=h)).json()
    assert any(item["kind"] == "mcem" for item in customer_timeline)


@pytest.mark.asyncio
async def test_scope_changes_invalidate_confirmation_and_loss_preserves_history(api):
    owner, _, _, deal, note = await setup(api)
    h = owner["headers"]
    path = f"/deals/{deal['id']}"
    await prepare(api, owner, deal)
    for key in ["fit", "problem", "outcome", "solution"]:
        await confirm(api, owner, deal, note, key)
    await api.patch(path, json={"stage": "proposal"}, headers=h)
    changed = await api.patch(path + "/mcem/journey", json={"scope": "New scope, including supplier onboarding"}, headers=h)
    assert changed.status_code == 200
    solution = next(m for m in changed.json()["milestones"] if m["key"] == "solution")
    assert solution["needs_review"] and solution["status"] == "in_progress" and solution["evidence"]
    assert any(e["kind"] == "confirmation_review_required" for e in changed.json()["events"])
    assert (await api.patch(path, json={"stage": "negotiation"}, headers=h)).status_code == 409
    assert (await api.patch(path, json={"stage": "lost"}, headers=h)).status_code == 409
    before = (await api.get(path + "/mcem", headers=h)).json()
    assert (await api.patch(path, json={"stage": "lost", "lost_reason": "Budget deferred"}, headers=h)).status_code == 200
    after = (await api.get(path + "/mcem", headers=h)).json()
    assert after["phase"] == before["phase"] and after["journey"]["state"] == "paused"
    loss = next(e for e in after["events"] if e["kind"] == "stage_changed" and e["detail"]["to"] == "lost")
    assert loss["detail"]["from"] == "proposal" and loss["detail"]["reason"] == "Budget deferred"
    assert (await api.patch(path + "/mcem/journey", json={"scope": "Edit lost history"}, headers=h)).status_code == 409


@pytest.mark.asyncio
async def test_evidence_dates_sources_tenancy_and_viewer_permissions(api):
    owner, _, _, deal, note = await setup(api)
    other, _, _, other_deal, other_note = await setup(api)
    path = f"/deals/{deal['id']}/mcem"
    body = {"kind": "note", "ref_id": other_note["id"], "explanation": "A different customer's workshop", "occurred_on": str(TODAY)}
    assert (await api.post(path + "/milestones/fit/evidence", json=body, headers=owner["headers"])).status_code == 404
    body.update(ref_id=note["id"], occurred_on=str(TODAY + timedelta(days=1)))
    assert (await api.post(path + "/milestones/fit/evidence", json=body, headers=owner["headers"])).status_code == 409
    assert (await api.get(path, headers=other["headers"])).status_code == 404
    assert (await api.get(path)).status_code == 401
    assert (await api.patch(path + "/journey", json={"delivery_owner_id": str(other["user_id"])}, headers=owner["headers"])).status_code == 409
    assert (await api.post(path + "/milestones/fit/evidence", json={"kind": "link", "url": "javascript:alert(1)", "explanation": "A fake agreement", "occurred_on": str(TODAY)}, headers=owner["headers"])).status_code == 422
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(User).where(User.id == owner["user_id"]).values(role=UserRole.VIEWER))
        await db.commit()
    assert (await api.get(path, headers=owner["headers"])).status_code == 200
    assert (await api.patch(path + "/journey", json={"scope": "Viewer change"}, headers=owner["headers"])).status_code == 403


@pytest.mark.asyncio
async def test_import_cannot_bypass_gates_and_legacy_records_stay_usable(api):
    owner, customer, _, deal, _ = await setup(api)
    from app.services.data_service import ImportService
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        user = await db.get(User, owner["user_id"])
        result = await ImportService(db, user).run("deals", [{"title": deal["title"], "customer": customer["name"], "stage": "won"}], True)
        assert result["errors"] and result["updated"] == 0
        await db.commit()
    assert (await api.get(f"/deals/{deal['id']}", headers=owner["headers"])).json()["stage"] == "lead"
    legacy = await api.post("/deals", json={"title": "Imported legacy sale", "customer_id": customer["id"], "stage": "proposal"}, headers=owner["headers"])
    assert legacy.status_code == 201 and not legacy.json()["mcem_enabled"]
    assert (await api.patch(f"/deals/{legacy.json()['id']}", json={"stage": "won"}, headers=owner["headers"])).status_code == 200
    invalid = await api.post("/deals", json={"title": "Skipping evidence", "customer_id": customer["id"], "stage": "won", "mcem_enabled": True}, headers=owner["headers"])
    assert invalid.status_code == 409


@pytest.mark.asyncio
async def test_due_reporting_and_team_reminders_are_deduplicated_without_email(api):
    owner, _, _, deal, _ = await setup(api)
    path = f"/deals/{deal['id']}/mcem"
    response = await api.patch(path + "/milestones/fit", json={"status": "in_progress", "due_date": str(TODAY - timedelta(days=1))}, headers=owner["headers"])
    assert response.status_code == 200
    report = (await api.get("/mcem/report", headers=owner["headers"])).json()
    assert report["overdue_milestones"] == 1 and len(report["opportunities"]) == 1
    before = len(api.queued)
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        assert await McemService(db).remind(TODAY) == 1
        assert await McemService(db).remind(TODAY) == 0
    assert not any(name.endswith("send_platform_email_task") for name, _ in api.queued[before:])
