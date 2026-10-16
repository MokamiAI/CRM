"""Roles hold against real requests: a viewer reads but changes nothing, staff
do day-to-day work but not manager actions, and only an admin manages people."""
import pytest

from .conftest import mark_verified, new_company

ITEM = [{"description": "Platter (serves 10)", "quantity": "1", "unit_price": "650", "tax_rate": "15"}]


async def _member(api, admin_headers: dict, role: str) -> dict:
    email = f"{role}-{admin_headers['Authorization'][-10:].lower()}@example.com".replace("_", "-")
    res = await api.post("/users", json={"email": email, "password": "Correct-Horse-9", "full_name": f"A {role}", "role": role}, headers=admin_headers)
    assert res.status_code == 201, res.text
    await mark_verified(email)
    login = await api.post("/auth/login", json={"email": email, "password": "Correct-Horse-9"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_viewer_reads_but_changes_nothing(api):
    owner = await new_company(api, "Theta Traders")
    admin = owner["headers"]
    customer = (await api.post("/customers", json={"name": "Shop A"}, headers=admin)).json()
    viewer = await _member(api, admin, "viewer")

    for path in ("/customers", "/quotes", "/invoices", "/deals", f"/customers/{customer['id']}"):
        assert (await api.get(path, headers=viewer)).status_code == 200, path

    attempts = [
        ("post", "/customers", {"name": "Not allowed"}),
        ("patch", f"/customers/{customer['id']}", {"name": "Renamed"}),
        ("post", "/quotes", {"customer_id": customer["id"], "issue_date": "2026-10-14", "items": ITEM}),
        ("post", "/invoices", {"customer_id": customer["id"], "issue_date": "2026-10-14", "items": ITEM}),
        ("post", "/products", {"name": "Thing", "unit_price": "1"}),
        ("post", "/deals", {"title": "Deal", "customer_id": customer["id"]}),
    ]
    for method, path, body in attempts:
        res = await getattr(api, method)(path, json=body, headers=viewer)
        assert res.status_code == 403, f"{method.upper()} {path}: {res.status_code}"

    names = [c["name"] for c in (await api.get("/customers", headers=admin)).json()]
    assert names == ["Shop A"]


@pytest.mark.asyncio
async def test_staff_work_but_cannot_manage(api):
    owner = await new_company(api, "Iota Installers")
    admin = owner["headers"]
    staff = await _member(api, admin, "staff")
    customer = (await api.post("/customers", json={"name": "Client B"}, headers=staff)).json()
    invoice = (await api.post("/invoices", json={"customer_id": customer["id"], "issue_date": "2026-10-14", "items": ITEM}, headers=staff)).json()
    assert invoice.get("status") == "draft"
    await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=staff)

    # Manager actions and people management are out of reach.
    assert (await api.post(f"/invoices/{invoice['id']}/void", headers=staff)).status_code == 403
    assert (await api.post(f"/customers/{customer['id']}/deactivate", headers=staff)).status_code == 403
    assert (await api.get("/users", headers=staff)).status_code == 403
    assert (await api.post("/users", json={"email": "x@example.com", "password": "Correct-Horse-9", "full_name": "X", "role": "admin"}, headers=staff)).status_code == 403
    assert (await api.get("/billing/payments", headers=staff)).status_code == 403
