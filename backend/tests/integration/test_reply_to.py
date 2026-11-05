"""Where clients' replies go. Without a connected mailbox (and with YGT's
inbound mail off) replies go to the company's own addresses: its chosen
reply addresses, else its sender email, never a domain nobody receives
mail for. The Messages page shows the same address."""
import pytest

from app.models.company_settings import CompanySettings
from app.services.email_settings import resolve_email_config

from .conftest import new_company


def _company(**kw):
    base = dict(company_name="Acme Ltd", sender_name=None, sender_email="sales@acme.test", smtp_host=None, smtp_port=None,
                smtp_username=None, smtp_password=None, smtp_use_tls=True, reply_to_emails=None)
    base.update(kw)
    return CompanySettings(**base)


def test_chosen_reply_addresses_win_else_the_sender_email(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "SMTP_FROM_EMAIL", "billing@yougt.co.za")
    assert resolve_email_config(_company()).reply_to == "sales@acme.test"
    both = resolve_email_config(_company(reply_to_emails="billing@yougt.co.za, johannes@yougt.co.za"))
    assert both.reply_to == "billing@yougt.co.za, johannes@yougt.co.za"


@pytest.mark.asyncio
async def test_settings_take_up_to_three_reply_addresses_and_messages_shows_them(api):
    owner = await new_company(api, "Reply Co")
    h = owner["headers"]
    await api.patch("/settings", json={"sender_email": "hello@replyco.co.za"}, headers=h)
    # No mailbox, no inbound mail: the line shows the company's own address.
    assert (await api.get("/conversations/inbox-address", headers=h)).json()["address"] == "hello@replyco.co.za"

    saved = await api.patch("/settings", json={"reply_to_emails": " Billing@ReplyCo.co.za; johannes@replyco.co.za "}, headers=h)
    assert saved.status_code == 200, saved.text
    assert saved.json()["reply_to_emails"] == "billing@replyco.co.za, johannes@replyco.co.za"
    address = (await api.get("/conversations/inbox-address", headers=h)).json()["address"]
    assert address == "billing@replyco.co.za, johannes@replyco.co.za" and "example.com" not in address

    assert (await api.patch("/settings", json={"reply_to_emails": "a@x.co, b@x.co, c@x.co, d@x.co"}, headers=h)).status_code == 422
    assert (await api.patch("/settings", json={"reply_to_emails": "not-an-email"}, headers=h)).status_code == 422
    # Cleared: back to the sender email.
    await api.patch("/settings", json={"reply_to_emails": ""}, headers=h)
    assert (await api.get("/conversations/inbox-address", headers=h)).json()["address"] == "hello@replyco.co.za"
