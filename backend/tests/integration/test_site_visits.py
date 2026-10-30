"""Website visits counted without cookies, the admin report and the nightly email."""
import uuid

import pytest

from app.core.config import settings
from app.services import site_visits
from app.tasks.visitor_tasks import send_daily_report
from .conftest import new_company

PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"
COMPUTER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0 Safari/537.36"


def visit(api, ua, **body):
    return api.post("/public/visit", json={"path": "/", **body}, headers={"User-Agent": ua})


@pytest.mark.asyncio
async def test_visits_are_counted_once_a_day_per_visitor_and_reported(api, monkeypatch):
    admin = await new_company(api, "Visitor admin")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAILS", admin["email"])
    report = lambda: api.get("/admin/visitors", params={"days": 1}, headers=admin["headers"])  # noqa: E731
    before = (await report()).json()

    phone, computer = f"{PHONE} t{uuid.uuid4().hex}", f"{COMPUTER} t{uuid.uuid4().hex}"
    for body in [{"path": "/assessment", "src": "qr"}, {"path": "/assessment", "event": "checkup_start", "src": "qr"},
                 {"path": "/assessment", "event": "checkup_done", "src": "qr"}, {"path": "/register/", "src": "qr"}]:
        assert (await visit(api, phone, **body)).status_code == 204
    assert (await visit(api, computer, referrer="https://www.google.co.za/search?q=crm")).status_code == 204
    # Not counted: bots, pages that aren't public, made-up events.
    await visit(api, "Googlebot/2.1 (+http://www.google.com/bot.html)")
    await visit(api, computer, path="/invoices")
    await visit(api, computer, event="purchase")

    after = (await report()).json()
    assert after["visitors"] - before["visitors"] == 2
    assert after["page_views"] - before["page_views"] == 3
    assert after["checkups_started"] - before["checkups_started"] == 1
    assert after["checkups_finished"] - before["checkups_finished"] == 1
    sources = {s["source"]: s["visitors"] for s in after["sources"]}
    assert sources["QR code"] >= 1 and sources["Google"] >= 1
    assert {"Check-up", "Sign-up page", "Home"} <= {p["name"] for p in after["pages"]}
    assert len(after["by_day"]) == 1

    # Only YGT's team sees the report.
    stranger = await new_company(api, "Not YGT")
    assert (await api.get("/admin/visitors", headers=stranger["headers"])).status_code == 403


@pytest.mark.asyncio
async def test_sources_and_devices():
    assert site_visits.source_of("qr", "https://www.google.com/") == "QR code"
    assert site_visits.source_of(None, "https://l.facebook.com/l.php?u=x") == "Facebook"
    assert site_visits.source_of(None, "https://www.google.co.za/") == "Google"
    assert site_visits.source_of(None, None) == "Direct"
    assert site_visits.source_of(None, settings.FRONTEND_URL + "/about") == "Direct"
    assert site_visits.source_of(None, "https://blog.example.org/post") == "blog.example.org"
    assert site_visits.device_of(PHONE) == "phone" and site_visits.device_of(COMPUTER) == "computer"


@pytest.mark.asyncio
async def test_nightly_report_goes_to_the_support_inbox(api, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_EMAIL", "founder@example.com")
    await visit(api, f"{PHONE} t{uuid.uuid4().hex}", path="/about")
    before = len(api.queued)
    assert await send_daily_report() == 1
    (name, (email,)), = api.queued[before:]
    assert name.endswith("send_platform_email_task") and email["to"] == "founder@example.com"
    assert email["subject"].startswith("Website: ") and "/admin/visitors" in email["html"]
    assert "Started the check-up" in email["text"]
