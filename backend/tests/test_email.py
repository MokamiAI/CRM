import smtplib
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.email_dispatch import commit_and_enqueue
from app.services import email_service
from app.services.email_service import EmailNotConfiguredError, OutgoingEmail, render_email, send_email
from app.services.email_settings import EffectiveEmailConfig
from app.services.notification_service import NotificationService
from app.tasks import email_tasks


def _company(**overrides):
    values = dict(
        company_name="Acme Ltd",
        address="1 Main Road\nCape Town",
        tax_number="4123456789",
        logo_url=None,
        default_currency="ZAR",
        email_signature=None,
        document_template={},
    )
    return SimpleNamespace(**(values | overrides))


def _context(company):
    return NotificationService(db=None)._base_context(company)


def _invoice():
    item = SimpleNamespace(
        description="Consulting <hours>",
        quantity=Decimal("2.00"),
        unit_price=Decimal("1500.00"),
        line_total=Decimal("3000.00"),
    )
    return SimpleNamespace(
        invoice_number="INV-0007",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        subtotal=Decimal("3000.00"),
        tax_total=Decimal("450.00"),
        total=Decimal("3450.00"),
        amount_paid=Decimal("0.00"),
        notes=None,
        po_number=None,
        reference=None,
        items=[item],
    )


def _config(**overrides):
    values = dict(
        host="smtp.example.com",
        port=587,
        username="user",
        password="secret",
        use_tls=True,
        from_email="billing@acme.test",
        from_name="Acme Billing",
    )
    return EffectiveEmailConfig(**(values | overrides))


class TestRendering:
    def test_invoice_email_has_html_and_text_bodies(self):
        company = _company()
        invoice = _invoice()
        email = render_email(
            "invoice_sent",
            to="jane@customer.test",
            subject="Invoice INV-0007 from Acme Ltd",
            customer=SimpleNamespace(name="Jane", tax_number=None),
            invoice=invoice,
            amount_due=invoice.total - invoice.amount_paid,
            **_context(company),
        )
        for body in (email.html, email.text):
            assert "Grow · Manage · Succeed" in body
            assert "INV-0007" in body
            assert "ZAR 3,450.00" in body
            assert "31 Oct 2026" in body
        assert "<html>" in email.html
        assert "<html>" not in email.text
        # Quantities drop the trailing ".00".
        assert "2 x ZAR 1,500.00" in email.text

    def test_html_escapes_user_input_but_text_does_not(self):
        email = render_email(
            "invoice_sent",
            to="x@customer.test",
            subject="s",
            customer=SimpleNamespace(name="<script>alert(1)</script>", tax_number=None),
            invoice=_invoice(),
            amount_due=Decimal("1"),
            **_context(_company()),
        )
        assert "<script>" not in email.html
        assert "&lt;script&gt;" in email.html
        assert "Consulting &lt;hours&gt;" in email.html
        assert "<script>" in email.text

    def test_payment_receipt_says_paid_in_full_only_when_settled(self):
        def render(balance):
            return render_email(
                "payment_receipt",
                to="x@customer.test",
                subject="s",
                customer=SimpleNamespace(name="Jane", tax_number=None),
                invoice=_invoice(),
                payment=SimpleNamespace(
                    amount=Decimal("100"),
                    paid_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
                    reference="EFT-1",
                ),
                balance=balance,
                **_context(_company()),
            )

        assert "paid in full" in render(Decimal("0")).text
        assert "paid in full" not in render(Decimal("50")).text

    @pytest.mark.parametrize("template", ["quote_sent", "test_email"])
    def test_other_templates_render(self, template):
        quote = _invoice()
        quote.quote_number = "QUO-0003"
        quote.expiry_date = None
        email = render_email(
            template,
            to="x@customer.test",
            subject="s",
            customer=SimpleNamespace(name="Jane", tax_number=None),
            quote=quote,
            **_context(_company()),
        )
        assert "Acme Ltd" in email.html and "Acme Ltd" in email.text

    def test_emails_without_document_settings_still_show_the_vat_number(self):
        # Messages and campaign emails pass only the company; the shared
        # footer used to crash on the VAT label for VAT-registered companies.
        email = render_email(
            "conversation_message",
            to="x@customer.test",
            subject="Your order",
            paragraphs=[["Hello"]],
            author_name="Thabo",
            signature=None,
            company=_company(document_template={"tax_label": "VAT reg. no."}),
        )
        assert "VAT reg. no.: 4123456789" in email.html
        assert "Grow · Manage · Succeed" in email.html
        assert email.text.rstrip().endswith("Grow · Manage · Succeed")

    @pytest.mark.parametrize("sender", ["billing@ygt.test", "no-reply@ygt.test"])
    def test_platform_footer_keeps_sender_guidance_and_adds_tagline(self, monkeypatch, sender):
        from app.core.config import settings
        from app.services.platform_email import compose

        monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", sender)
        monkeypatch.setattr(settings, "PUBLIC_SUPPORT_EMAIL", "support@ygt.test")
        email = compose("person@example.com", "Ticket update", "An update", ["We're working on your ticket."])
        assert "Grow · Manage · Succeed" in email.html
        assert email.text.rstrip().endswith("Grow · Manage · Succeed")
        if sender.startswith("no-reply"):
            assert "Replies to it aren't received" in email.text
            assert "support@ygt.test" in email.html


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(f"login:{username}:{password}")

    def send_message(self, message):
        self.calls.append("send")
        self.sent = message


class _FakeSMTPSSL(_FakeSMTP):
    pass


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", _FakeSMTPSSL)
    return _FakeSMTP.instances


class TestSending:
    email = OutgoingEmail(to="jane@customer.test", subject="Hello", html="<p>Hi</p>", text="Hi")

    def test_port_587_uses_starttls_then_login(self, fake_smtp):
        send_email(_config(), self.email)
        (smtp,) = fake_smtp
        assert type(smtp) is _FakeSMTP
        assert smtp.calls == ["starttls", "login:user:secret", "send", "quit"]
        assert smtp.sent["From"] == "Acme Billing <billing@acme.test>"
        assert smtp.sent["To"] == "jane@customer.test"
        assert smtp.sent.is_multipart()

    def test_port_465_uses_implicit_tls(self, fake_smtp):
        send_email(_config(port=465), self.email)
        (smtp,) = fake_smtp
        assert type(smtp) is _FakeSMTPSSL
        assert "starttls" not in smtp.calls

    def test_no_login_without_username(self, fake_smtp):
        send_email(_config(username=None, use_tls=False), self.email)
        assert fake_smtp[0].calls == ["send", "quit"]

    @pytest.mark.parametrize("missing", ["host", "from_email"])
    def test_unconfigured_raises_without_connecting(self, fake_smtp, missing):
        with pytest.raises(EmailNotConfiguredError):
            send_email(_config(**{missing: None if missing == "host" else ""}), self.email)
        assert fake_smtp == []


class TestDelivery:
    email = OutgoingEmail(to="jane@customer.test", subject="s", html="h", text="t")

    def _patch(self, monkeypatch, email, send=None):
        sent = []
        monkeypatch.setattr(email_tasks, "run_async", lambda fn: (_config(), email))
        monkeypatch.setattr(email_tasks, "send_email", send or (lambda config, e: sent.append(e)))
        return sent

    def test_sends_composed_email(self, monkeypatch):
        sent = self._patch(monkeypatch, self.email)
        assert email_tasks._deliver(lambda s: None, "invoice x") is True
        assert sent == [self.email]

    def test_skips_customer_without_email(self, monkeypatch):
        sent = self._patch(monkeypatch, None)
        assert email_tasks._deliver(lambda s: None, "invoice x") is False
        assert sent == []

    def test_unconfigured_email_is_skipped_not_retried(self, monkeypatch):
        def send(config, email):
            raise EmailNotConfiguredError()

        self._patch(monkeypatch, self.email, send)
        assert email_tasks._deliver(lambda s: None, "invoice x") is False

    def test_smtp_errors_propagate_for_celery_retry(self, monkeypatch):
        def send(config, email):
            raise smtplib.SMTPServerDisconnected("gone")

        self._patch(monkeypatch, self.email, send)
        with pytest.raises(OSError):
            email_tasks._deliver(lambda s: None, "invoice x")
        assert OSError in email_tasks.send_invoice_email_task.autoretry_for


class _FakeDB:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")


class _FakeTask:
    name = "fake_task"

    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def delay(self, *args):
        if self.fail:
            raise ConnectionError("redis down")
        self.log.append(("delay", args))


class TestDispatch:
    @pytest.mark.asyncio
    async def test_commits_before_enqueueing(self):
        log = []
        await commit_and_enqueue(_FakeDB(log), _FakeTask(log), "abc")
        assert log == ["commit", ("delay", ("abc",))]

    @pytest.mark.asyncio
    async def test_queue_failure_does_not_fail_the_request(self):
        log = []
        await commit_and_enqueue(_FakeDB(log), _FakeTask(log, fail=True), "abc")
        assert log == ["commit"]


class TestSender:
    """Who an email says it's from, and where replies go."""

    @pytest.fixture(autouse=True)
    def _platform(self, monkeypatch):
        from app.services import email_settings

        monkeypatch.setattr(email_settings.settings, "SMTP_HOST", "smtp.ygt.test")
        monkeypatch.setattr(email_settings.settings, "SMTP_FROM_EMAIL", "billing@ygt.test")

    def _company(self, **values):
        base = dict(company_name="Acme Ltd", sender_name=None, sender_email="sales@acme.test", smtp_host=None,
                    smtp_port=None, smtp_username=None, smtp_password=None, smtp_use_tls=None)
        return SimpleNamespace(**(base | values))

    def test_shared_server_sends_from_ygt_with_replies_to_the_company(self):
        from app.services.email_settings import resolve_email_config

        config = resolve_email_config(self._company())
        assert (config.from_email, config.from_name, config.reply_to) == ("billing@ygt.test", "Acme Ltd", "sales@acme.test")

    def test_own_server_sends_from_the_company(self):
        from app.services.email_settings import resolve_email_config

        config = resolve_email_config(self._company(smtp_host="mail.acme.test", sender_name="Acme Sales"))
        assert (config.from_email, config.from_name, config.reply_to) == ("sales@acme.test", "Acme Sales", None)

    def test_company_without_email_settings_uses_shared_sender(self, monkeypatch):
        from app.services import email_settings
        from app.services.email_settings import resolve_email_config

        monkeypatch.setattr(email_settings.settings, "SMTP_FROM_EMAIL", "billing@yougt.co.za")
        config = resolve_email_config(self._company(sender_email=None))
        assert config.host == "smtp.ygt.test"
        assert (config.from_email, config.from_name, config.reply_to) == ("billing@yougt.co.za", "Acme Ltd", None)

    def test_reply_to_header_is_added_unless_the_email_sets_its_own(self, monkeypatch):
        from app.services.email_settings import resolve_email_config

        sent = []
        monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *a, **k: _Capture(sent))
        config = resolve_email_config(self._company())
        send_email(config, OutgoingEmail(to="c@x.test", subject="s", html="<p>h</p>", text="h"))
        send_email(config, OutgoingEmail(to="c@x.test", subject="s", html="<p>h</p>", text="h", headers={"Reply-To": "reply+t@in.test"}))
        assert sent[0]["Reply-To"] == "sales@acme.test" and sent[0]["From"] == "Acme Ltd <billing@ygt.test>"
        assert sent[1]["Reply-To"] == "reply+t@in.test"


class _Capture:
    def __init__(self, sent):
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, **kwargs):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        self.sent.append(message)


def test_ygt_emails_are_no_reply_and_point_to_public_support(monkeypatch):
    """Sent from the no-reply address on the mail account's domain, with no
    Reply-To; the footer names the public support address, never the
    private inbox."""
    from app.core.config import settings
    from app.services import platform_email

    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "noreply@yougt.co.za")
    monkeypatch.setattr(settings, "SUPPORT_EMAIL", "owner@gmail.com")
    monkeypatch.setattr(settings, "PUBLIC_SUPPORT_EMAIL", "support@yougt.co.za")
    cfg = platform_email.platform_config()
    assert cfg.from_email == "noreply@yougt.co.za" and cfg.reply_to is None

    mail = platform_email.compose(to="someone@example.com", subject="Hi", title="Hi", paragraphs=["Hello"])
    assert "Reply-To" not in mail.headers
    for body in (mail.text, mail.html):
        assert "support@yougt.co.za" in body and "Replies to it aren" in body and "owner@gmail.com" not in body

    # To the YGT team (with the sender as Reply-To): no no-reply line.
    team = platform_email.compose(to="owner@gmail.com", subject="Contact", title="Contact", paragraphs=["Hi"], reply_to="visitor@example.com")
    assert team.headers["Reply-To"] == "visitor@example.com" and "Replies to it aren" not in team.text

    # From a real mailbox (billing@), replies are read: no no-reply line.
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "billing@yougt.co.za")
    assert platform_email.platform_config().from_email == "billing@yougt.co.za"
    plain = platform_email.compose(to="someone@example.com", subject="Hi", title="Hi", paragraphs=["Hello"])
    assert "Replies to it aren" not in plain.text and "owner@gmail.com" not in plain.text
