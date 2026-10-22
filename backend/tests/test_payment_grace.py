"""Unpaid: three days with everything working, then view-only."""
from datetime import datetime, timedelta, timezone

from app.core.plans import GRACE_DAYS, LOCKED
from app.models.billing import Subscription
from app.services.billing_service import effective

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def sub(**values):
    return Subscription(plan="grow", interval="monthly", seats=2, **values)


def test_an_ended_trial_has_three_days_to_pay_then_becomes_view_only():
    ended = NOW - timedelta(days=1)
    grace = effective(sub(status="trialing", trial_ends_at=ended), NOW)
    assert grace.state == "trial_grace" and not grace.locked and grace.pay_by == ended + timedelta(days=GRACE_DAYS)
    late = effective(sub(status="trialing", trial_ends_at=NOW - timedelta(days=GRACE_DAYS, minutes=1)), NOW)
    assert late.state == "trial_ended" and late.plan is LOCKED and late.pay_by is None


def test_a_running_trial_or_paid_period_has_no_pay_by_date():
    assert effective(sub(status="trialing", trial_ends_at=NOW + timedelta(days=5)), NOW).pay_by is None
    assert effective(sub(status="active", current_period_end=NOW + timedelta(days=5)), NOW).pay_by is None


def test_a_missed_renewal_has_three_days_to_pay_then_becomes_view_only():
    due = NOW - timedelta(days=2)
    unpaid = effective(sub(status="past_due", current_period_end=due), NOW)
    assert unpaid.state == "past_due" and not unpaid.locked and unpaid.pay_by == due + timedelta(days=GRACE_DAYS)
    lapsed = effective(sub(status="past_due", current_period_end=NOW - timedelta(days=GRACE_DAYS + 1)), NOW)
    assert lapsed.state == "lapsed" and lapsed.locked
    # Cancelled by them: paid up to the end of the period, no extra days.
    assert effective(sub(status="cancelled", current_period_end=NOW - timedelta(hours=1)), NOW).locked
