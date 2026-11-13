"""Run: python -m pytest scripts/watch -q"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("server_watch", Path(__file__).with_name("server_watch.py"))
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


def test_one_email_when_it_starts_a_reminder_later_and_one_when_it_clears():
    state, t = {}, 1_000_000.0
    new, ongoing, fixed = sw.decide(state, {"container:celery_worker": "worker down"}, t)
    assert new == ["worker down"] and not ongoing and not fixed
    # Five minutes later, still down: no second email.
    assert sw.decide(state, {"container:celery_worker": "worker down"}, t + 300) == ([], [], [])
    # Six hours on: a reminder.
    _, ongoing, _ = sw.decide(state, {"container:celery_worker": "worker down"}, t + 6 * 3600)
    assert len(ongoing) == 1 and "since" in ongoing[0]
    # Fixed: one "back to normal".
    new, ongoing, fixed = sw.decide(state, {}, t + 6 * 3600 + 300)
    assert not new and not ongoing and fixed[0].startswith("Back to normal: worker down")
    assert state["open"] == {}


def test_slow_signs_must_last_before_an_email():
    state, t = {}, 1_000_000.0
    # Memory needs 3 checks in a row (15 minutes).
    assert sw.decide(state, {"memory": "low"}, t)[0] == []
    assert sw.decide(state, {"memory": "low"}, t + 300)[0] == []
    assert sw.decide(state, {"memory": "low"}, t + 600)[0] == ["low"]


def test_a_blip_that_never_reached_an_email_clears_quietly():
    state, t = {}, 1_000_000.0
    sw.decide(state, {"site": "slow"}, t)  # one slow answer: not yet
    assert sw.decide(state, {}, t + 300) == ([], [], [])


def test_env_file_values_are_read_without_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('SMTP_HOST="smtp.example.com"\n# note\nSMTP_PORT=465\n')
    assert sw.read_env(f) == {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465"}
