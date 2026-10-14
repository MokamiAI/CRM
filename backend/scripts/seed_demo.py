"""Fills a LOCAL YGT with one realistic demo company, for testing and screenshots.

    YGT_ENV_FILE=../.env.local python scripts/seed_demo.py    (from backend/, API running)

Creates "Demo Catering Co" on a Scale trial (sign in: demo.admin@example.com / DemoPass-2026) with
customers, contacts, products, deals at every stage, quotes (draft, sent,
accepted into a draft invoice, rejected), invoices (draft, sent, part-paid,
paid, overdue), activities, a supplier and purchase order, and a support
ticket. Nothing is emailed: every send uses notify=false.

Refuses to run unless both the API and the database are on this machine.
"""
import asyncio
import os
import sys
from datetime import date, timedelta
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import update  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.tenancy import set_system  # noqa: E402
from app.models.user import User  # noqa: E402

API = os.environ.get("YGT_API", "http://127.0.0.1:8000/api/v1")
EMAIL, PASSWORD = "demo.admin@example.com", "DemoPass-2026"
LOCAL = ("localhost", "127.0.0.1", "::1")
today = date.today()


def d(days: int) -> str:
    return (today + timedelta(days=days)).isoformat()


def check(res: httpx.Response) -> dict:
    if res.status_code >= 400:
        sys.exit(f"{res.request.method} {res.request.url} -> {res.status_code}: {res.text[:300]}")
    return res.json()


def main() -> None:
    for name, url in (("YGT_API", API), ("DATABASE_URL", settings.DATABASE_URL)):
        if urlsplit(url).hostname not in LOCAL:
            sys.exit(f"Refusing: {name} is not on this machine ({urlsplit(url).hostname}). This script is for local testing only.")

    c = httpx.Client(base_url=API, timeout=60)
    res = c.post("/auth/register", json={"company_name": "Demo Catering Co", "full_name": "Thandi Mokoena", "email": EMAIL, "password": PASSWORD, "plan": "scale"})
    if res.status_code == 409:
        sys.exit(f"{EMAIL} already exists: the demo company is already seeded. Drop and recreate ygt_dev to start over.")
    c.headers["Authorization"] = f"Bearer {check(res)['access_token']}"

    customers = {}
    for name, email, phone, vat in [
        ("Naledi Events", "bookings@naledievents.example.com", "082 555 0101", "4123456789"),
        ("Sizwe Construction", "accounts@sizwecon.example.com", "083 555 0102", "4987654321"),
        ("Bright Minds Academy", "finance@brightminds.example.com", "011 555 0103", None),
        ("Thabo Dlamini", "thabo.dlamini@example.com", "084 555 0104", None),
        ("Kopano Community Trust", "admin@kopanotrust.example.com", "012 555 0105", None),
        ("Lerato Legal Services", "office@leratolegal.example.com", "021 555 0106", "4555666777"),
    ]:
        customers[name] = check(c.post("/customers", json={"name": name, "email": email, "phone": phone, "tax_number": vat, "billing_address": "12 Loop Street\nCape Town\n8001"}))
    for cust, first, last, title in [("Naledi Events", "Naledi", "Khumalo", "Owner"), ("Sizwe Construction", "Sizwe", "Ndlovu", "Site manager"), ("Bright Minds Academy", "Grace", "Mahlangu", "Bursar")]:
        check(c.post(f"/customers/{customers[cust]['id']}/contacts", json={"first_name": first, "last_name": last, "title": None, "job_title": title, "is_primary": True}))

    for name, price in [("Catering per guest", "280.00"), ("Platter (serves 10)", "650.00"), ("Delivery and setup", "750.00"), ("Waiter per hour", "120.00"), ("Cake (tiered)", "1800.00")]:
        check(c.post("/products", json={"name": name, "unit_price": price, "tax_rate": "15"}))

    deal_ids = {}
    for title, cust, stage, value, close in [
        ("Wedding, 120 guests", "Naledi Events", "proposal", "38400", 21),
        ("Site lunches, October", "Sizwe Construction", "negotiation", "24000", 10),
        ("Prize-giving buffet", "Bright Minds Academy", "qualified", "15500", 35),
        ("Birthday platters", "Thabo Dlamini", "lead", "3250", 45),
        ("Fundraiser dinner", "Kopano Community Trust", "won", "27000", -5),
        ("Office year-end", "Lerato Legal Services", "lost", "18000", -12),
    ]:
        deal = check(c.post("/deals", json={"title": title, "customer_id": customers[cust]["id"], "stage": stage, "value": value, "expected_close_date": d(close)}))
        deal_ids[title] = deal["id"]
    check(c.patch(f"/deals/{deal_ids['Office year-end']}", json={"lost_reason": "Chose a cheaper caterer"}))

    for kind, subject, due, cust in [
        ("call", "Confirm guest numbers with Naledi", 0, "Naledi Events"),
        ("meeting", "Menu tasting at Sizwe site office", 2, "Sizwe Construction"),
        ("task", "Send revised prize-giving quote", -1, "Bright Minds Academy"),
        ("email", "Thank Kopano Trust for the booking", 1, "Kopano Community Trust"),
    ]:
        check(c.post("/activities", json={"type": kind, "subject": subject, "due_date": d(due), "customer_id": customers[cust]["id"]}))

    def quote(cust: str, items: list, ref: str, deal: str | None = None) -> dict:
        return check(c.post("/quotes", json={"customer_id": customers[cust]["id"], "deal_id": deal_ids.get(deal), "issue_date": d(-3), "expiry_date": d(27), "reference": ref, "items": items, "notes": "Prices include delivery within 30 km."}))

    wedding = quote("Naledi Events", [{"description": "Catering per guest", "quantity": "120", "unit_price": "280", "tax_rate": "15"}, {"description": "Cake (tiered)", "quantity": "1", "unit_price": "1800", "tax_rate": "15"}], "Wedding, 120 guests", "Wedding, 120 guests")
    check(c.post(f"/quotes/{wedding['id']}/send", params={"notify": "false"}))
    lunches = quote("Sizwe Construction", [{"description": "Site lunch per worker", "quantity": "200", "unit_price": "120", "tax_rate": "15"}], "October site lunches", "Site lunches, October")
    check(c.post(f"/quotes/{lunches['id']}/send", params={"notify": "false"}))
    check(c.post(f"/quotes/{lunches['id']}/accept"))  # becomes a draft invoice
    quote("Bright Minds Academy", [{"description": "Platter (serves 10)", "quantity": "12", "unit_price": "650", "tax_rate": "15"}], "Prize-giving", "Prize-giving buffet")
    lost = quote("Lerato Legal Services", [{"description": "Catering per guest", "quantity": "40", "unit_price": "280", "tax_rate": "15"}], "Office year-end", "Office year-end")
    check(c.post(f"/quotes/{lost['id']}/send", params={"notify": "false"}))
    check(c.post(f"/quotes/{lost['id']}/reject"))

    def invoice(cust: str, items: list, ref: str, issued: int, due: int) -> dict:
        return check(c.post("/invoices", json={"customer_id": customers[cust]["id"], "issue_date": d(issued), "due_date": d(due), "reference": ref, "items": items}))

    paid = invoice("Kopano Community Trust", [{"description": "Fundraiser dinner per guest", "quantity": "90", "unit_price": "260", "tax_rate": "15"}, {"description": "Waiter per hour", "quantity": "24", "unit_price": "120", "tax_rate": "15"}], "Fundraiser dinner", -20, -5)
    check(c.post(f"/invoices/{paid['id']}/send", params={"notify": "false"}))
    check(c.post(f"/invoices/{paid['id']}/payments", json={"amount": paid["total"], "method": "eft", "reference": "KOPANO-FUND"}))
    part = invoice("Naledi Events", [{"description": "Wedding deposit (50%)", "quantity": "1", "unit_price": "16800", "tax_rate": "15"}], "Wedding deposit", -7, 7)
    check(c.post(f"/invoices/{part['id']}/send", params={"notify": "false"}))
    check(c.post(f"/invoices/{part['id']}/payments", json={"amount": "8000.00", "method": "eft", "reference": "NALEDI-DEP"}))
    late = invoice("Thabo Dlamini", [{"description": "Platter (serves 10)", "quantity": "2", "unit_price": "650", "tax_rate": "15"}], "Birthday platters", -40, -10)
    check(c.post(f"/invoices/{late['id']}/send", params={"notify": "false"}))
    check(c.post("/invoices/refresh-overdue"))
    invoice("Bright Minds Academy", [{"description": "Staff meeting snacks", "quantity": "3", "unit_price": "650", "tax_rate": "15"}], "Staff meeting", 0, 30)

    supplier = check(c.post("/suppliers", json={"name": "Fresh Farms Wholesale", "contact_name": "Pieter van Wyk", "email": "orders@freshfarms.example.com", "phone": "021 555 0199"}))
    check(c.post("/purchase-orders", json={"supplier_id": supplier["id"], "issue_date": d(0), "delivery_date": d(5), "reference": "Wedding, 120 guests", "items": [{"description": "Chicken portions (kg)", "quantity": "40", "unit_price": "89", "tax_rate": "15"}, {"description": "Fresh vegetables (box)", "quantity": "12", "unit_price": "210", "tax_rate": "15"}]}))

    # A monthly contract that started two months ago: three drafts so far.
    first = (today.replace(day=1) - timedelta(days=40)).replace(day=min(today.day, 28))
    check(c.post("/recurring-invoices", json={"customer_id": customers["Bright Minds Academy"]["id"], "frequency": "monthly", "start_date": first.isoformat(), "due_days": 14, "reference": "Staff-room catering contract", "items": [{"description": "Staff-room catering (monthly)", "quantity": "1", "unit_price": "5200", "tax_rate": "15"}]}))

    check(c.post("/support/tickets", json={"subject": "How do I add my banking details?", "category": "question", "body": "Where do I put our bank account so it shows on invoices?"}))

    # Confirm the demo admin's email, so the YGT admin pages work locally too
    # (PLATFORM_ADMIN_EMAILS in .env.local lists demo.admin@example.com).
    async def verify() -> None:
        async with AsyncSessionLocal() as db:
            set_system(db)
            await db.execute(update(User).where(User.email == EMAIL).values(email_verified_at=date.today()))
            await db.commit()
        await engine.dispose()

    asyncio.run(verify())
    print(f"Seeded Demo Catering Co. Sign in at http://localhost:4173/login as {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
