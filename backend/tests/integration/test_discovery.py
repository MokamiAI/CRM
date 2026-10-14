"""Discovery finds leads in a company's own records and nearby on
OpenStreetMap, never twice, only for its own company, and only adds them
to the pipeline when a person says so."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_system
from app.models.crm import Deal
from app.models.discovery import DiscoverySettings
from app.models.quote import Quote
from app.services import discovery_osm
from app.tasks.discovery_tasks import _run_company

from .conftest import new_company

TODAY = date.today()
ITEM = [{"description": "Catering", "quantity": "1", "unit_price": "1000", "tax_rate": "15"}]


async def _system(stmt):
    async with AsyncSessionLocal() as db:
        set_system(db)
        result = await db.execute(stmt)
        await db.commit()
        return result


async def _customer(api, h, name: str) -> str:
    return (await api.post("/customers", json={"name": name}, headers=h)).json()["id"]


async def _own_records_company(api):
    """A Scale company with one customer of each kind Discovery looks for."""
    owner = await new_company(api, f"Disco {uuid.uuid4().hex[:4]}", plan="scale")
    h = owner["headers"]
    quiet, lost, quoted, busy = [await _customer(api, h, n) for n in ("Quiet Co", "Lost Co", "Quoted Co", "Busy Co")]
    # Quiet: paid 200 days ago, nothing since.
    inv = (await api.post("/invoices", json={"customer_id": quiet, "issue_date": (TODAY - timedelta(days=200)).isoformat(), "items": ITEM}, headers=h)).json()
    await api.post(f"/invoices/{inv['id']}/send", params={"notify": "false"}, headers=h)
    await api.post(f"/invoices/{inv['id']}/payments", json={"amount": inv["total"], "method": "eft"}, headers=h)
    # Lost 90 days ago.
    deal = (await api.post("/deals", json={"title": "Year-end function", "customer_id": lost, "stage": "lost", "value": "18000"}, headers=h)).json()
    await _system(update(Deal).where(Deal.id == uuid.UUID(deal["id"])).values(closed_at=datetime.now(timezone.utc) - timedelta(days=90)))
    # A quote sent 30 days ago, never answered.
    quote = (await api.post("/quotes", json={"customer_id": quoted, "issue_date": (TODAY - timedelta(days=30)).isoformat(), "items": ITEM}, headers=h)).json()
    await api.post(f"/quotes/{quote['id']}/send", params={"notify": "false"}, headers=h)
    # Busy: an unanswered quote too, but an open deal already, so skipped.
    q2 = (await api.post("/quotes", json={"customer_id": busy, "issue_date": (TODAY - timedelta(days=30)).isoformat(), "items": ITEM}, headers=h)).json()
    await api.post(f"/quotes/{q2['id']}/send", params={"notify": "false"}, headers=h)
    await api.post("/deals", json={"title": "Open", "customer_id": busy, "stage": "proposal"}, headers=h)
    return owner, {"quiet": quiet, "lost": lost, "quoted": quoted, "busy": busy}, quote


@pytest.mark.asyncio
async def test_finds_own_records_once_and_adds_on_request(api):
    owner, ids, quote = await _own_records_company(api)
    h = owner["headers"]
    queued_before = len(api.queued)

    run = await api.post("/discovery/run", headers=h)
    assert run.status_code == 200 and run.json() == {"found": 3, "looking_nearby": False}
    leads = (await api.get("/discovery/leads", headers=h)).json()
    by_source = {lead["source"]: lead for lead in leads}
    assert set(by_source) == {"quiet_customer", "lost_deal", "stale_quote"}
    assert by_source["quiet_customer"]["customer_id"] == ids["quiet"]
    assert by_source["lost_deal"]["details"]["value"] == "18000.00"
    assert by_source["stale_quote"]["details"]["number"] == quote["quote_number"]
    assert ids["busy"] not in {lead["customer_id"] for lead in leads}
    assert api.queued[queued_before:] == []  # running by hand emails nobody

    # Straight away again: refused. Through the service: nothing new.
    assert (await api.post("/discovery/run", headers=h)).status_code == 429
    async with AsyncSessionLocal() as db:
        from app.core.tenancy import set_tenant
        from app.services.discovery_service import DiscoveryService

        set_tenant(db, owner["company_id"])
        assert await DiscoveryService(db).run(TODAY) == []
        await db.commit()

    # Add the quote lead: a Lead deal worth the quote, tied to the quote.
    lead = by_source["stale_quote"]
    added = await api.post(f"/discovery/leads/{lead['id']}/add", json={"title": "Follow up quote"}, headers=h)
    assert added.status_code == 200 and added.json()["status"] == "added"
    deal = (await api.get(f"/deals/{added.json()['deal_id']}", headers=h)).json()
    assert deal["stage"] == "lead" and deal["title"] == "Follow up quote" and deal["customer_id"] == ids["quoted"]
    assert float(deal["value"]) == float(quote["total"])
    linked = (await _system(select(Quote.deal_id).where(Quote.id == uuid.UUID(quote["id"])))).scalar()
    assert str(linked) == deal["id"]
    assert (await api.post(f"/discovery/leads/{lead['id']}/add", headers=h)).status_code == 409

    # Dismiss one: it leaves the list and doesn't come back.
    gone = by_source["lost_deal"]
    assert (await api.post(f"/discovery/leads/{gone['id']}/dismiss", headers=h)).json()["status"] == "dismissed"
    remaining = (await api.get("/discovery/leads", headers=h)).json()
    assert [r["source"] for r in remaining] == ["quiet_customer"]
    assert (await api.get("/discovery/counts", headers=h)).json() == {"new": 1, "added": 1, "dismissed": 1}


FAKE_OVERPASS = {
    "elements": [
        {"type": "node", "id": 1, "tags": {"name": "Sunrise Primary School", "amenity": "school", "phone": "011 555 0001", "website": "sunrise.example.com", "addr:street": "Main Rd", "addr:city": "Soweto"}},
        {"type": "way", "id": 2, "tags": {"name": "Little Stars Creche", "amenity": "kindergarten", "email": "not-an-email"}},
        {"type": "node", "id": 3, "tags": {"name": "Known Academy (Pty) Ltd", "amenity": "school"}},  # already a customer
        {"type": "node", "id": 4, "tags": {"amenity": "school"}},  # no name
        {"type": "node", "id": 5, "tags": {"name": "Corner Cafe", "amenity": "cafe"}},  # not a chosen industry
    ]
}


@pytest.fixture
def fake_osm(monkeypatch):
    calls = []

    class Res:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    async def fake_get(url, **kwargs):
        calls.append(url)
        if "nominatim" in url:
            q = kwargs["params"]["q"]
            return Res([] if q == "Nowhere at all" else [{"lat": "-26.2485", "lon": "27.8540", "display_name": "Soweto, Johannesburg"}])
        assert "amenity" in kwargs["data"]["data"] and "around:5000" in kwargs["data"]["data"]
        return Res(FAKE_OVERPASS)

    monkeypatch.setattr(discovery_osm, "_get", fake_get)
    return calls


@pytest.mark.asyncio
async def test_nearby_businesses_from_openstreetmap(api, fake_osm):
    owner = await new_company(api, "Pi Caterers", plan="scale")
    h = owner["headers"]
    await _customer(api, h, "Known Academy")

    bad = await api.put("/discovery/settings", json={"area": "Nowhere at all", "radius_km": 5, "industries": ["education"]}, headers=h)
    assert bad.status_code == 422 and bad.json()["error_code"] == "DISCOVERY_AREA_NOT_FOUND"
    conf = (await api.put("/discovery/settings", json={"area": "Soweto", "radius_km": 5, "industries": ["education"]}, headers=h)).json()
    assert conf["located"] is True and conf["industries"] == ["education"]

    # Own records answer at once; the map lookup finishes after the reply.
    assert (await api.post("/discovery/run", headers=h)).json() == {"found": 0, "looking_nearby": True}
    assert (await api.get("/discovery/settings", headers=h)).json()["nearby_status"] == "done"
    leads = {lead["name"]: lead for lead in (await api.get("/discovery/leads", headers=h)).json()}
    assert set(leads) == {"Sunrise Primary School", "Little Stars Creche"}
    school = leads["Sunrise Primary School"]
    assert school["source"] == "osm" and school["kind"] == "school" and school["industry"] == "education"
    assert school["website"] == "https://sunrise.example.com" and school["address"] == "Main Rd, Soweto"
    assert leads["Little Stars Creche"]["email"] is None  # bad email dropped

    added = (await api.post(f"/discovery/leads/{school['id']}/add", headers=h)).json()
    customer = (await api.get(f"/customers/{added['customer_id']}", headers=h)).json()
    assert customer["name"] == "Sunrise Primary School" and customer["phone"] == "011 555 0001"
    deal = (await api.get(f"/deals/{added['deal_id']}", headers=h)).json()
    assert deal["stage"] == "lead" and deal["industry"] == "education"


@pytest.mark.asyncio
async def test_scale_only_roles_and_other_companies(api, fake_osm):
    grow = await new_company(api, "Rho Repairs")
    res = await api.get("/discovery/leads", headers=grow["headers"])
    assert res.status_code == 402 and res.json()["error_code"] == "PLAN_FEATURE_DISCOVERY"

    owner, _, _ = await _own_records_company(api)
    await api.post("/discovery/run", headers=owner["headers"])
    lead_id = (await api.get("/discovery/leads", headers=owner["headers"])).json()[0]["id"]

    # A viewer can look but not add, dismiss, run or change settings.
    viewer_email = f"{uuid.uuid4().hex[:10]}@example.com"
    invite = await api.post("/users", json={"email": viewer_email, "full_name": "Vee Viewer", "role": "viewer", "password": "Correct-Horse-9"}, headers=owner["headers"])
    assert invite.status_code == 201, invite.text
    login = await api.post("/auth/login", json={"email": viewer_email, "password": "Correct-Horse-9"})
    vh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await api.get("/discovery/leads", headers=vh)).status_code == 200
    assert (await api.post(f"/discovery/leads/{lead_id}/add", headers=vh)).status_code == 403
    assert (await api.post(f"/discovery/leads/{lead_id}/dismiss", headers=vh)).status_code == 403
    assert (await api.post("/discovery/run", headers=vh)).status_code == 403
    assert (await api.put("/discovery/settings", json={}, headers=vh)).status_code == 403

    other = await new_company(api, "Sigma Scale", plan="scale")
    assert (await api.get("/discovery/leads", headers=other["headers"])).json() == []
    assert (await api.post(f"/discovery/leads/{lead_id}/add", headers=other["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_weekly_run_emails_admins_only_when_something_is_new(api, fake_osm, monkeypatch):
    owner, _, _ = await _own_records_company(api)
    before = len(api.queued)
    assert await _run_company(owner["company_id"]) == 3
    sent = api.queued[before:]
    assert len(sent) == 1 and sent[0][0] == "app.tasks.platform_tasks.send_platform_email_task"
    email = sent[0][1][0]
    assert email["to"] == owner["email"] and "3 new leads" in email["subject"]
    assert "Quoted Co" in email["text"] and "/discovery" in email["text"]

    # Next week, nothing new: no email.
    await _system(update(DiscoverySettings).where(DiscoverySettings.company_id == owner["company_id"]).values(last_run_at=None))
    assert await _run_company(owner["company_id"]) == 0
    assert len(api.queued) == before + 1

    # Off: skipped. On Grow: skipped.
    await _system(update(DiscoverySettings).where(DiscoverySettings.company_id == owner["company_id"]).values(enabled=False))
    assert await _run_company(owner["company_id"]) is None
    grow = await new_company(api, "Tau Traders")
    assert await _run_company(grow["company_id"]) is None


def test_overpass_query_and_parse():
    query = discovery_osm.build_query(-26.2, 27.9, 80, ["legal", "other"])
    assert "around:50000" in query  # capped at 50 km
    assert '["office"~"^(lawyer|notary)$"]' in query
    places = discovery_osm.parse({"elements": [{"type": "node", "id": 9, "tags": {"name": "  Dube   Attorneys ", "office": "lawyer", "phone": "011 1;011 2"}}]}, ["legal"])
    assert places[0].name == "Dube Attorneys" and places[0].phone == "011 1" and places[0].ref == "osm:node/9"



@pytest.mark.asyncio
async def test_map_outage_keeps_own_records_and_backup_server_is_tried(api, monkeypatch):
    from app.core.config import settings

    tried = []

    async def busy_then_ok(url, **kwargs):
        tried.append(url)
        if "nominatim" in url:
            return type("R", (), {"json": lambda self: [{"lat": "-33.92", "lon": "18.42", "display_name": "Cape Town"}]})()
        if "second" not in url:
            raise discovery_osm.OsmUnavailable("504")
        return type("R", (), {"json": lambda self: FAKE_OVERPASS})()

    monkeypatch.setattr(discovery_osm, "_get", busy_then_ok)
    monkeypatch.setattr(settings, "OVERPASS_URL", "https://first.example/api,https://second.example/api")
    places = await discovery_osm.nearby(-33.9, 18.4, 5, ["education"])
    assert len(places) == 3 and tried == ["https://first.example/api", "https://second.example/api"]

    # Every map server down: the run still saves leads from the company's own records.
    monkeypatch.setattr(settings, "OVERPASS_URL", "https://first.example/api")
    owner, _, _ = await _own_records_company(api)
    h = owner["headers"]
    assert (await api.put("/discovery/settings", json={"area": "Cape Town", "radius_km": 5, "industries": ["education"]}, headers=h)).status_code == 200
    res = (await api.post("/discovery/run", headers=h)).json()
    assert res == {"found": 3, "looking_nearby": True}
    assert len((await api.get("/discovery/leads", headers=h)).json()) == 3
    assert (await api.get("/discovery/settings", headers=h)).json()["nearby_status"] == "failed"
