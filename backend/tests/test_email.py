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
