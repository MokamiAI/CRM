"""Booking slots, calendar invites, import parsing, rate limits, and what
each plan unlocks."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.middleware import _MemoryCounter
from app.core.plans import CUSTOM_FIELDS, LOCKED, MARKETING, PLANS, PRIORITY_SUPPORT, TEAM_CHAT, TRIAL_PLAN, WHATSAPP_SMS
from app.schemas.platform import Availability
from app.services.booking_service import free_slots
from app.services.data_service import RowError, _date, _money, _stage
from app.services.platform_email import ics_invite

# Monday 12 Oct 2026, 08:00 in Johannesburg (06:00 UTC)
MONDAY_8AM = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


def test_slots_follow_the_hours_notice_and_bookings():
    rules = Availability(weekdays=[0, 1, 2, 3, 4], start="09:00", end="11:00", slot_minutes=30, min_notice_hours=2, days_ahead=6)
    taken = {datetime(2026, 10, 13, 7, 30, tzinfo=timezone.utc)}  # Tue 09:30 SAST
    days = free_slots(rules, taken, MONDAY_8AM)
    assert [d.date for d in days] == [date(2026, 10, d) for d in (12, 13, 14, 15, 16)]  # no weekend
    # Monday: 2 hours' notice from 08:00 means 10:00 is the first slot.
    assert [s.astimezone(timezone(timedelta(hours=2))).strftime("%H:%M") for s in days[0].slots] == ["10:00", "10:30"]
    # Tuesday: four slots minus the booked 09:30.
    assert len(days[1].slots) == 3 and taken.isdisjoint(days[1].slots)


def test_blocked_days_and_switched_off():
    rules = Availability(blocked_dates=[date(2026, 10, 13)], min_notice_hours=0, days_ahead=2)
    assert date(2026, 10, 13) not in [d.date for d in free_slots(rules, set(), MONDAY_8AM)]


def test_calendar_invite_and_cancellation():
    start = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
    invite = ics_invite("booking-1@ygt", start, start + timedelta(minutes=30), "YGT session: Onboarding, with Acme; Ltd", "Notes, here", "support@ygt.test", [("Thandi", "t@acme.test")])
    assert "METHOD:REQUEST" in invite and "DTSTART:20261013T070000Z" in invite and "ATTENDEE;CN=Thandi" in invite
    assert "Acme\\; Ltd" in invite  # escaped
    assert all(len(line.encode()) <= 75 for line in invite.split("\r\n"))
    cancel = ics_invite("booking-1@ygt", start, start, "x", "y", "support@ygt.test", [], method="CANCEL", sequence=1)
    assert "METHOD:CANCEL" in cancel and "SEQUENCE:1" in cancel and "STATUS:CANCELLED" in cancel


@pytest.mark.parametrize(
    "raw, expected",
    [("R 1 234,50", "1234.50"), ("1,234.50", "1234.50"), ("1234.5", "1234.50"), ("1.234,56", "1234.56"), ("850", "850.00"), ("", None)],
)
def test_money_from_spreadsheets(raw, expected):
    assert _money(raw, "Price") == (Decimal(expected) if expected else None)


def test_dates_and_stages_from_spreadsheets():
    assert _date("31/10/2026") == _date("2026-10-31") == date(2026, 10, 31)
    assert _stage("Negotiation").value == "negotiation" and _stage("").value == "lead"
    with pytest.raises(RowError):
        _stage("maybe")
    with pytest.raises(RowError):
        _date("next week")


def test_rate_limit_window():
    counter = _MemoryCounter()

    async def run():
        hits = [await counter.hit("login:1.2.3.4", 60) for _ in range(12)]
        return [h[0] for h in hits]

    assert asyncio.run(run())[-1] == 12  # the middleware refuses once past the rule's limit (10)


def test_each_plan_gets_what_it_pays_for():
    """The features on each price card are exactly what the API allows."""
    assert PLANS["hustle"].features == frozenset()
    grow = {WHATSAPP_SMS, MARKETING, CUSTOM_FIELDS, TEAM_CHAT}
    assert PLANS["grow"].features == grow
    assert PLANS["scale"].features == grow | {PRIORITY_SUPPORT}
    assert PLANS[TRIAL_PLAN] is PLANS["grow"]  # the trial is Grow
    assert LOCKED.features == frozenset()
    assert PLANS["hustle"].user_limit(1) == 3 and PLANS["grow"].user_limit(7) == 7
