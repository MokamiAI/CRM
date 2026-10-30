"""A team chat message tells everyone else in the company (bell and push,
never email); unread news from one channel stays one notification that
counts the messages; opening the channel reads it."""
import pytest

from .conftest import new_company
from .test_team_tasks import _bell, _member


def team_notes(bell):
    return [n for n in bell["items"] if n["kind"] == "team_message"]


@pytest.mark.asyncio
async def test_team_messages_notify_the_rest_of_the_team(api):
    admin = await new_company(api, "Chatty team")
    staff, _ = await _member(api, admin)
    viewer, _ = await _member(api, admin, role="viewer")
    stranger = await new_company(api, "Another company")
    channel = (await api.get("/team-chat/channels", headers=admin["headers"])).json()[0]
    post = lambda headers, body: api.post(f"/team-chat/channels/{channel['id']}/messages", json={"body": body}, headers=headers)  # noqa: E731

    before = len(api.queued)
    assert (await post(admin["headers"], "Morning team, the Mokoena quote went out")).status_code == 201
    assert not [n for n, _ in api.queued[before:] if n.endswith("send_platform_email_task")], "chat must not email"

    for headers in (staff, viewer):
        notes = team_notes(await _bell(api, headers))
        assert len(notes) == 1 and notes[0]["read_at"] is None
        assert notes[0]["params"]["count"] == 1 and notes[0]["params"]["text"].startswith("Morning team")
        assert notes[0]["link"] == f"/messages?tab=team&ch={channel['id']}"
    assert team_notes(await _bell(api, admin["headers"])) == []  # not the sender
    assert team_notes(await _bell(api, stranger["headers"])) == []  # not another company

    # Two more: still one notification, counting three, showing the latest.
    await post(admin["headers"], "Second")
    await post(admin["headers"], "Third " + "x" * 300)
    (note,) = team_notes(await _bell(api, staff))
    assert note["params"]["count"] == 3 and note["params"]["text"].endswith("…") and len(note["params"]["text"]) == 140

    # Opening the channel reads it; the next message starts a fresh count.
    await api.get(f"/team-chat/channels/{channel['id']}/messages", headers=staff)
    assert team_notes(await _bell(api, staff))[0]["read_at"] is not None
    assert team_notes(await _bell(api, viewer))[0]["read_at"] is None
    await post(viewer, "Viewers can chat too")
    (note,) = team_notes(await _bell(api, staff))
    assert note["read_at"] is None and note["params"]["count"] == 1 and note["params"]["by"] == "Lerato Dube"
    # The viewer's own message doesn't notify the viewer.
    assert team_notes(await _bell(api, viewer))[0]["params"]["count"] == 3
