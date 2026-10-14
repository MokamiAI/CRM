"""Recurring invoice dates keep the start day, clamp to short months, and
never drift (31 Jan, 28 Feb, 31 Mar, not 31 Jan, 28 Feb, 28 Mar)."""
from datetime import date
from types import SimpleNamespace

from app.services.recurring_service import add_months, next_cycle


def _run(frequency: str, start: date, count: int) -> list[date]:
    schedule = SimpleNamespace(frequency=frequency, start_date=start)
    dates = [start]
    while len(dates) < count:
        dates.append(next_cycle(schedule, dates[-1]))
    return dates


def test_month_end_clamps_without_drifting():
    assert _run("monthly", date(2026, 1, 31), 5) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]


def test_leap_years():
    assert _run("monthly", date(2028, 1, 31), 2) == [date(2028, 1, 31), date(2028, 2, 29)]
    assert _run("yearly", date(2028, 2, 29), 3) == [date(2028, 2, 29), date(2029, 2, 28), date(2030, 2, 28)]


def test_quarterly_weekly_and_year_end():
    assert _run("quarterly", date(2026, 11, 30), 3) == [date(2026, 11, 30), date(2027, 2, 28), date(2027, 5, 30)]
    assert _run("weekly", date(2026, 12, 28), 3) == [date(2026, 12, 28), date(2027, 1, 4), date(2027, 1, 11)]
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
