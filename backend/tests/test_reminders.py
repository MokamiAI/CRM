from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.company_settings import CompanySettingsUpdate
from app.services.email_service import render_email
from app.services.notification_service import NotificationService
from app.services.reminder_service import pick_reminder_step

SCHEDULE = [-3, 0, 7, 14]


@pytest.mark.parametrize(
    ("days_past_due", "expected"),
    [
        (-10, None),  # first step (3 days before) not reached yet
        (-4, None),
        (-3, -3),
        (-1, -3),  # still on the "due soon" step
        (0, 0),
        (6, 0),
        (7, 7),
        (13, 7),
        (14, 14),
        (90, 14),  # long overdue: last step only, never a burst of old ones
    ],
)
def test_pick_reminder_step(days_past_due, expected):
    assert pick_reminder_step(SCHEDULE, days_past_due) == expected


def test_pick_reminder_step_empty_schedule():
    assert pick_reminder_step([], 30) is None


def test_offsets_are_deduplicated_and_sorted():
    update = CompanySettingsUpdate(reminder_offsets=[14, 0, -3, 7, 0])
    assert update.reminder_offsets == [-3, 0, 7, 14]


@pytest.mark.parametrize("bad", [[-61], [366], list(range(11))])
def test_offsets_out_of_range_are_rejected(bad):
    with pytest.raises(ValidationError):
        CompanySettingsUpdate(reminder_offsets=bad)


def _render(days_past_due, amount_paid="0.00"):
    company = SimpleNamespace(company_name="Acme Ltd", address=None, tax_number=None, logo_url=None, default_currency="ZAR", email_signature=None, document_template={})
    invoice = SimpleNamespace(
        invoice_number="INV-0009",
        due_date=date(2026, 10, 10),
        total=Decimal("1000.00"),
        amount_paid=Decimal(amount_paid),
    )
    return render_email(
        "invoice_reminder",
        to="x@customer.example.com",
        subject="s",
        customer=SimpleNamespace(name="Jane"),
        invoice=invoice,
        amount_due=invoice.total - invoice.amount_paid,
        days_past_due=days_past_due,
        **NotificationService(db=None)._base_context(company),
    )


def test_reminder_wording_follows_the_due_date():
    assert "due on 10 Oct 2026, in 3 days" in _render(-3).text
    assert "due on 10 Oct 2026, in 1 day." in _render(-1).text
    assert "is due today" in _render(0).text
    assert "1 day overdue" in _render(1).text
    assert "7 days overdue" in _render(7).html


def test_reminder_shows_part_payment_and_remaining_balance():
    email = _render(7, amount_paid="400.00")
    assert "Already paid: ZAR 400.00" in email.text
    assert "Amount due:   ZAR 600.00" in email.text
    assert "Already paid" not in _render(7).text
