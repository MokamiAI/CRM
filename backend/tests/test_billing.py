"""What a company can use, worked out from its subscription and the clock."""
import uuid
from datetime import datetime, timedelta, timezone

from app.core.plans import GRACE_DAYS, PLANS, TRIAL_USERS
from app.models.billing import Subscription
from app.services.billing_service import _add_interval, effective, new_trial

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def sub(**kwargs) -> Subscription:
    return Subscription(company_id=uuid.uuid4(), **kwargs)


def test_trial_is_grow_until_it_ends():
    trial = sub(plan="grow", status="trialing", seats=TRIAL_USERS, trial_ends_at=NOW + timedelta(days=1))
    assert (effective(trial, NOW).plan.key, effective(trial, NOW).users) == ("grow", TRIAL_USERS)
    # No free plan: once the trial ends the company is read-only.
    ended = effective(trial, NOW + timedelta(days=2))
    assert (ended.plan.key, ended.state, ended.locked) == ("none", "trial_ended", True)


def test_new_trial_lasts_the_configured_days():
    trial = new_trial(uuid.uuid4())
    assert trial.status == "trialing" and trial.plan == "grow"
    assert timedelta(days=13) < trial.trial_ends_at - datetime.now(timezone.utc) <= timedelta(days=14)


def test_paid_plan_users_and_grace():
    paid = sub(plan="grow", status="active", seats=4, current_period_end=NOW)
    assert (effective(paid, NOW - timedelta(days=1)).plan.key, effective(paid, NOW - timedelta(days=1)).users) == ("grow", 4)
    # Paystack retries a failed card for a few days before it lapses.
    assert effective(paid, NOW + timedelta(days=GRACE_DAYS - 1)).plan.key == "grow"
    assert effective(paid, NOW + timedelta(days=GRACE_DAYS + 1)).state == "lapsed"


def test_cancelled_keeps_the_plan_to_the_end_of_the_period_only():
    cancelled = sub(plan="scale", status="cancelled", seats=5, current_period_end=NOW)
    assert effective(cancelled, NOW - timedelta(hours=1)).plan.key == "scale"
    assert effective(cancelled, NOW + timedelta(hours=1)).locked


def test_hustle_is_per_company_with_three_people():
    hustle = sub(plan="hustle", status="active", seats=1, current_period_end=NOW + timedelta(days=5))
    assert effective(hustle, NOW).users == 3


def test_prices_per_seat_cheaper_from_three():
    # Hustle: one price for the company, however many of its three use it.
    assert PLANS["hustle"].price_cents("monthly", 1) == PLANS["hustle"].price_cents("monthly", 3) == 19_900
    # Grow and Scale, one or two seats: the full price per seat.
    assert PLANS["grow"].price_cents("monthly", 1) == 22_900
    assert PLANS["grow"].price_cents("monthly", 2) == 45_800
    assert PLANS["scale"].price_cents("monthly", 2) == 59_800
    # From three seats every seat is at the team price.
    assert PLANS["grow"].price_cents("monthly", 3) == 44_700
    assert PLANS["scale"].price_cents("monthly", 7) == 174_300
    # Annual: ten months for twelve, at the same seat price.
    assert PLANS["grow"].price_cents("annually", 1) == 229_000
    assert PLANS["scale"].price_cents("annually", 5) == 1_245_000
    # One person never pays less for Grow than for Hustle, nor for Scale than Grow.
    assert PLANS["hustle"].price_cents("monthly", 1) < PLANS["grow"].price_cents("monthly", 1)
    for n in range(1, 12):
        assert PLANS["grow"].price_cents("monthly", n) < PLANS["scale"].price_cents("monthly", n)


def test_billing_periods():
    assert _add_interval(datetime(2026, 1, 31, tzinfo=timezone.utc), "monthly") == datetime(2026, 2, 28, tzinfo=timezone.utc)
    assert _add_interval(datetime(2026, 12, 15, tzinfo=timezone.utc), "monthly") == datetime(2027, 1, 15, tzinfo=timezone.utc)
    assert _add_interval(datetime(2028, 2, 29, tzinfo=timezone.utc), "annually") == datetime(2029, 2, 28, tzinfo=timezone.utc)


def test_trial_is_the_plan_chosen_at_sign_up():
    hustle = effective(new_trial(uuid.uuid4(), "hustle"))
    assert (hustle.plan.key, hustle.users, hustle.state) == ("hustle", 3, "trialing")
    assert hustle.plan.features == frozenset()  # what Hustle pays for, nothing more
    scale = effective(new_trial(uuid.uuid4(), "scale"))
    assert scale.plan.key == "scale" and "priority_support" in scale.plan.features and scale.users == TRIAL_USERS
    assert effective(new_trial(uuid.uuid4(), "unknown")).plan.key == "grow"
