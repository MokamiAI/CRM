"""Payment reminders on WhatsApp: only when the company switched them on and
Meta approved the template; with a Pay now button when online payments are
on; filed under Messages; and a number can be registered with its PIN."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.tenancy import set_tenant
from app.models.messaging import Conversation, Message
from app.services import channel_providers as providers
from app.services.online_payment_service import pay_token
from app.services.whatsapp_reminder_service import PLAIN, WITH_BUTTON, WhatsAppReminderService

from .conftest import new_company


class FakeMeta:
    def __init__(self, monkeypatch):
        self.created: list[dict] = []
        self.sent: list[dict] = []
        self.registered: list[str] = []
        self.status = {WITH_BUTTON: "PENDING", PLAIN: "PENDING"}

        async def create(cfg, secrets, template):
            assert cfg["business_account_id"] == "waba-1" and secrets["access_token"] == "token-1"
            self.created.append(template)
            return "PENDING"

        async def statuses(cfg, secrets):
            return dict(self.status)

        async def send(cfg, secrets, to, name, language, body, button=None):
            self.sent.append({"to": to, "name": name, "body": body, "button": button})
            return f"wamid.{len(self.sent)}"

        async def register(cfg, secrets, pin):
            self.registered.append(pin)

        monkeypatch.setattr(providers, "meta_create_template", create)
        monkeypatch.setattr(providers, "meta_template_statuses", statuses)
        monkeypatch.setattr(providers, "meta_send_template", send)
        monkeypatch.setattr(providers, "meta_register", register)


async def _whatsapp(api, h, reminders=True, waba="waba-1"):
    settings = {"phone_number_id": "phone-1", "payment_reminders": reminders, **({"business_account_id": waba} if waba else {})}
    res = await api.put("/settings/channels/whatsapp", json={"provider": "meta", "enabled": True, "settings": settings, "secrets": {"access_token": "token-1"}}, headers=h)
    assert res.status_code == 200, res.text
    return res.json()


async def _invoice(api, h, phone="082 123 4567"):
    customer = (await api.post("/customers", json={"name": "Thandi Mokoena", "phone": phone, "email": "thandi@example.com"}, headers=h)).json()
    res = await api.post(
        "/invoices",
        json={"customer_id": customer["id"], "issue_date": date.today().isoformat(), "due_date": (date.today() + timedelta(days=7)).isoformat(),
              "items": [{"description": "Plumbing", "quantity": "1", "unit_price": "1000", "tax_rate": "15"}]},
        headers=h,
    )
    invoice = res.json()
    assert (await api.post(f"/invoices/{invoice['id']}/send", params={"notify": "false"}, headers=h)).status_code == 200
    return invoice


async def _send(company_id, invoice_id) -> str:
    async with AsyncSessionLocal() as db:
        set_tenant(db, company_id)
        outcome = await WhatsAppReminderService(db).send_reminder(invoice_id)
        await db.commit()
        return outcome


def test_the_meta_api_version_is_current():
    assert "/v26.0" in providers.GRAPH


@pytest.mark.asyncio
async def test_reminders_go_on_whatsapp_once_meta_approves_the_template(api, monkeypatch):
    meta = FakeMeta(monkeypatch)
    owner = await new_company(api, "Mokoena Plumbing")
    h, company = owner["headers"], owner["company_id"]
    invoice = await _invoice(api, h)

    # Not connected, then connected but switched off: nothing is sent.
    assert await _send(company, invoice["id"]) == "off"
    await _whatsapp(api, h, reminders=False)
    assert await _send(company, invoice["id"]) == "off"

    # Templates need the business account id.
    await _whatsapp(api, h, waba=None)
    res = await api.post("/settings/channels/whatsapp/templates", headers=h)
    assert res.status_code == 422 and "Business Account ID" in res.json()["message"]
    await _whatsapp(api, h)
    res = await api.post("/settings/channels/whatsapp/templates", headers=h)
    assert res.status_code == 200, res.text
    assert [t["name"] for t in meta.created] == [WITH_BUTTON, PLAIN] and all(t["category"] == "UTILITY" for t in meta.created)
    assert meta.created[0]["components"][1]["buttons"][0]["url"].endswith("/public/pay/{{1}}")
    assert res.json()[WITH_BUTTON] == "PENDING"

    # Saving the settings again keeps what Meta said about the templates,
    # even when the app sends the approvals back with the form.
    saved = await _whatsapp(api, h)
    assert saved["settings"]["templates"][PLAIN] == "PENDING"
    res = await api.put("/settings/channels/whatsapp", json={"provider": "meta", "enabled": True, "settings": {**saved["settings"], "payment_reminders": True}}, headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["settings"]["templates"][PLAIN] == "PENDING" and res.json()["settings"]["phone_number_id"] == "phone-1"

    # Waiting for Meta: nothing goes out.
    assert await _send(company, invoice["id"]) == "template not approved"
    assert meta.sent == []

    # Approved: the plain one (online payments are off).
    meta.status = {WITH_BUTTON: "APPROVED", PLAIN: "APPROVED"}
    assert (await api.get("/settings/channels/whatsapp/templates", headers=h)).json()[PLAIN] == "APPROVED"
    assert await _send(company, invoice["id"]) == "sent"
    assert meta.sent[-1]["name"] == PLAIN and meta.sent[-1]["to"] == "27821234567" and meta.sent[-1]["button"] is None
    assert meta.sent[-1]["body"][:4] == ["Thandi Mokoena", "Mokoena Plumbing", invoice["invoice_number"], "ZAR 1,150.00"]

    # Online payments on: the one with the Pay now button, carrying the pay link.
    assert (await api.put("/settings/channels/payments", json={"provider": "paystack", "enabled": True, "secrets": {"secret_key": "sk_test_x"}}, headers=h)).status_code == 200
    assert await _send(company, invoice["id"]) == "sent"
    import uuid

    assert meta.sent[-1]["name"] == WITH_BUTTON and meta.sent[-1]["button"] == pay_token(uuid.UUID(invoice["id"]))

    # Both are filed under Messages, in the customer's WhatsApp thread.
    async with AsyncSessionLocal() as db:
        set_tenant(db, company)
        threads = (await db.scalars(select(Conversation).where(Conversation.channel == "whatsapp"))).all()
        assert len(threads) == 1 and threads[0].contact_phone == "27821234567"
        messages = (await db.scalars(select(Message).where(Message.conversation_id == threads[0].id).order_by(Message.created_at))).all()
        assert len(messages) == 2 and all(m.direction == "out" and m.external_id for m in messages)
        assert "Pay now: " in messages[1].body and "Pay now" not in messages[0].body


@pytest.mark.asyncio
async def test_a_customer_without_a_phone_or_a_paid_invoice_gets_nothing(api, monkeypatch):
    meta = FakeMeta(monkeypatch)
    meta.status = {WITH_BUTTON: "APPROVED", PLAIN: "APPROVED"}
    owner = await new_company(api, "Quiet Carpentry")
    h, company = owner["headers"], owner["company_id"]
    await _whatsapp(api, h)
    await api.post("/settings/channels/whatsapp/templates", headers=h)
    no_phone = await _invoice(api, h, phone="")
    assert await _send(company, no_phone["id"]) == "no phone"
    paid = await _invoice(api, h)
    assert (await api.post(f"/invoices/{paid['id']}/payments", json={"amount": "1150", "method": "eft"}, headers=h)).status_code == 201
    assert await _send(company, paid["id"]) == "nothing due"
    assert meta.sent == []


@pytest.mark.asyncio
async def test_sending_a_reminder_queues_the_whatsapp_one_too(api, monkeypatch):
    FakeMeta(monkeypatch)
    owner = await new_company(api, "Queue Builders")
    h = owner["headers"]
    invoice = await _invoice(api, h)
    res = await api.post(f"/invoices/{invoice['id']}/remind", headers=h)
    assert res.status_code == 202, res.text
    names = [name for name, _ in api.queued]
    assert "app.tasks.email_tasks.send_invoice_reminder_task" in names and "app.tasks.messaging_tasks.send_whatsapp_reminder_task" in names


@pytest.mark.asyncio
async def test_registering_a_number_needs_a_six_digit_pin(api, monkeypatch):
    meta = FakeMeta(monkeypatch)
    owner = await new_company(api, "Register Roofing")
    h = owner["headers"]
    assert (await api.post("/settings/channels/whatsapp/register", json={"pin": "123456"}, headers=h)).status_code == 422  # not connected
    await _whatsapp(api, h)
    assert (await api.post("/settings/channels/whatsapp/register", json={"pin": "12ab56"}, headers=h)).status_code == 422
    res = await api.post("/settings/channels/whatsapp/register", json={"pin": "123456"}, headers=h)
    assert res.status_code == 200 and meta.registered == ["123456"]
