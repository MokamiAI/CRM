"""Recurring invoices make one DRAFT per cycle, priced like any invoice,
never sent, never twice, only for their own company."""
import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.database import AsyncSessionLocal
from sqlalchemy import update

from app.core.tenancy import set_system, set_tenant
from app.models.billing import Subscription
from app.services.recurring_service import RecurringInvoiceService, add_months
from app.tasks.recurring_tasks import _make_due_drafts

from .conftest import new_company

ITEMS = [
    {"description": "Monthly IT support retainer", "quantity": "1", "unit_price": "4500", "tax_rate": "15"},
    {"description": "Cloud backup (per seat)", "quantity": "5", "unit_price": "80", "tax_rate": "15"},
]


async def _schedule(api, owner, start: date, **extra) -> dict:
    customer = (await api.post("/customers", json={"name": f"Client {uuid.uuid4().hex[:6]}"}, headers=owner["headers"])).json()
    res = await api.post(
        "/recurring-invoices",
        json={"customer_id": customer["id"], "frequency": "monthly", "start_date": start.isoformat(), "due_days": 7, "reference": "Retainer", "items": ITEMS, **extra},
        headers=owner["headers"],
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_catches_up_once_per_cycle_as_drafts(api):
    owner = await new_company(api, "Mu Managed IT", plan="scale")
    start = add_months(date.today(), -2)
    queued_before = len(api.queued)
    schedule = await _schedule(api, owner, start)
    assert Decimal(schedule["total"]) == Decimal("5635.00")  # (4500 + 400) + 15%

    detail = (await api.get(f"/recurring-invoices/{schedule['id']}", headers=owner["headers"])).json()
    made = detail["invoices"]
    assert [m["issue_date"] for m in made] == [add_months(start, n).isoformat() for n in (2, 1, 0)]
    assert {m["status"] for m in made} == {"draft"}
    assert {Decimal(m["total"]) for m in made} == {Decimal("5635.00")}
    assert detail["next_run_date"] == add_months(start, 3).isoformat()

    invoice = (await api.get(f"/invoices/{made[0]['id']}", headers=owner["headers"])).json()
    assert invoice["recurring_invoice_id"] == schedule["id"] and invoice["reference"] == "Retainer"
    assert invoice["due_date"] == (add_months(start, 2) + timedelta(days=7)).isoformat()  # due_days=7
    assert len(invoice["items"]) == 2
    assert api.queued[queued_before:] == []  # nothing emailed

    # The daily job, run twice: nothing new until the next cycle.
    await _make_due_drafts()
    await _make_due_drafts()
    again = (await api.get(f"/recurring-invoices/{schedule['id']}", headers=owner["headers"])).json()
    assert len(again["invoices"]) == 3


@pytest.mark.asyncio
async def test_two_runs_at_once_make_one_draft(api):
    owner = await new_company(api, "Nu Cleaning", plan="scale")
    schedule = await _schedule(api, owner, add_months(date.today(), 1))  # nothing due yet
    schedule_id = uuid.UUID(schedule["id"])
    cycle_day = date.fromisoformat(schedule["next_run_date"])

    async def run():
        async with AsyncSessionLocal() as db:
            set_tenant(db, owner["company_id"])
            service = RecurringInvoiceService(db)
            made = await service.make_due(await service.get(schedule_id), cycle_day)
            await asyncio.sleep(0.3)  # hold the lock a moment
            await db.commit()
            return len(made)

    counts = await asyncio.gather(run(), run())
    assert sorted(counts) == [0, 1]
    detail = (await api.get(f"/recurring-invoices/{schedule['id']}", headers=owner["headers"])).json()
    assert len(detail["invoices"]) == 1


@pytest.mark.asyncio
async def test_pause_resume_end_and_other_companies(api):
    owner = await new_company(api, "Xi Accounting", plan="scale")
    h = owner["headers"]
    schedule = await _schedule(api, owner, date.today(), end_date=add_months(date.today(), 1).isoformat())
    sid = schedule["id"]
    assert len((await api.get(f"/recurring-invoices/{sid}", headers=h)).json()["invoices"]) == 1

    paused = (await api.post(f"/recurring-invoices/{sid}/pause", headers=h)).json()
    assert paused["active"] is False
    resumed = (await api.post(f"/recurring-invoices/{sid}/resume", headers=h)).json()
    assert resumed["active"] is True

    # Past the end date: the last cycle is made, then it switches itself off.
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        service = RecurringInvoiceService(db)
        await service.make_due(await service.get(uuid.UUID(sid)), add_months(date.today(), 3))
        await db.commit()
    ended = (await api.get(f"/recurring-invoices/{sid}", headers=h)).json()
    assert len(ended["invoices"]) == 2 and ended["active"] is False

    other = await new_company(api, "Omicron Events", plan="scale")
    assert (await api.get(f"/recurring-invoices/{sid}", headers=other["headers"])).status_code == 404
    assert (await api.get("/recurring-invoices", headers=other["headers"])).json() == []
    assert (await api.delete(f"/recurring-invoices/{sid}", headers=other["headers"])).status_code == 404

    # Deleting stops it; its invoices stay.
    assert (await api.delete(f"/recurring-invoices/{sid}", headers=h)).status_code == 204
    invoices = (await api.get("/invoices", headers=h)).json()
    assert len(invoices) == 2 and all(i["recurring_invoice_id"] is None for i in invoices)


@pytest.mark.asyncio
async def test_recurring_needs_grow_or_scale(api):
    """Hustle can't start or restart a schedule, and the run leaves a
    downgraded company's schedules waiting; it can still see and stop them."""
    grow_owner = await new_company(api, "Pi Grow")
    gcustomer = (await api.post("/customers", json={"name": "Client"}, headers=grow_owner["headers"])).json()
    ok = await api.post(
        "/recurring-invoices",
        json={"customer_id": gcustomer["id"], "frequency": "monthly", "start_date": date.today().isoformat(), "items": ITEMS},
        headers=grow_owner["headers"],
    )
    assert ok.status_code == 201, ok.text  # Grow includes recurring invoices

    grow = await new_company(api, "Pi Plumbing", plan="hustle")
    customer = (await api.post("/customers", json={"name": "Client"}, headers=grow["headers"])).json()
    res = await api.post(
        "/recurring-invoices",
        json={"customer_id": customer["id"], "frequency": "monthly", "start_date": date.today().isoformat(), "items": ITEMS},
        headers=grow["headers"],
    )
    assert res.status_code == 402 and res.json()["error_code"] == "PLAN_FEATURE_RECURRING_INVOICES"

    owner = await new_company(api, "Rho Bookkeeping", plan="scale")
    schedule = await _schedule(api, owner, add_months(date.today(), 1))  # first cycle next month
    async with AsyncSessionLocal() as db:
        set_system(db)
        await db.execute(update(Subscription).where(Subscription.company_id == owner["company_id"]).values(plan="hustle"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        assert await RecurringInvoiceService(db).make_all_due(add_months(date.today(), 2)) == 0
    h, sid = owner["headers"], schedule["id"]
    assert (await api.get(f"/recurring-invoices/{sid}", headers=h)).json()["invoices"] == []
    assert (await api.post(f"/recurring-invoices/{sid}/pause", headers=h)).status_code == 200
    assert (await api.post(f"/recurring-invoices/{sid}/resume", headers=h)).status_code == 402
    assert (await api.delete(f"/recurring-invoices/{sid}", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_edit_lines_and_move_the_next_date(api):
    owner = await new_company(api, "Delta Two", plan="scale")
    h = owner["headers"]
    schedule = await _schedule(api, owner, add_months(date.today(), 1))
    moved = date.fromisoformat(schedule["next_run_date"]) + timedelta(days=5)
    res = await api.patch(
        f"/recurring-invoices/{schedule['id']}",
        json={"next_run_date": moved.isoformat(), "reference": "Retainer 2027", "items": ITEMS[:1], "frequency": "monthly"},
        headers=h,
    )
    assert res.status_code == 200, res.text
    edited = res.json()
    assert edited["next_run_date"] == moved.isoformat() and edited["reference"] == "Retainer 2027"
    assert Decimal(edited["total"]) == Decimal("5175.00")  # 4500 + 15%
    async with AsyncSessionLocal() as db:
        set_tenant(db, owner["company_id"])
        service = RecurringInvoiceService(db)
        made = await service.make_due(await service.get(uuid.UUID(schedule["id"])), moved)
        await db.commit()
    assert [m.issue_date for m in made] == [moved]
    after = (await api.get(f"/recurring-invoices/{schedule['id']}", headers=h)).json()
    assert after["next_run_date"] == add_months(moved, 1).isoformat()  # counts from the new date
