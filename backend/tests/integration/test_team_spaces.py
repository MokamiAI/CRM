"""Team chat spaces: only the people chosen see a space; Grow has one besides
General, Scale as many as it likes; replies, edits, reactions, files and
@mentions; a space can be deleted, General can't."""
import pytest

from .conftest import new_company
from .test_team_tasks import _bell, _member


async def _channels(api, headers):
    res = await api.get("/team-chat/channels", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_a_space_is_only_for_its_members(api):
    admin = await new_company(api, "Spaces Grow")
    staff, staff_id = await _member(api, admin)
    outsider, _ = await _member(api, admin)
    general = (await _channels(api, admin["headers"]))[0]
    assert general["is_general"] and not general["is_private"]

    res = await api.post("/team-chat/channels", json={"name": "Sales", "member_ids": [staff_id]}, headers=admin["headers"])
    assert res.status_code == 201, res.text
    space = res.json()
    assert space["is_private"] and staff_id in space["member_ids"] and len(space["member_ids"]) == 2  # creator too

    assert [c["name"] for c in await _channels(api, staff)] == ["General", "Sales"]
    assert [c["name"] for c in await _channels(api, outsider)] == ["General"]
    assert (await api.get(f"/team-chat/channels/{space['id']}/messages", headers=outsider)).status_code == 404

    # Only members hear about its messages.
    assert (await api.post(f"/team-chat/channels/{space['id']}/messages", json={"body": "Pipeline review at 10"}, headers=admin["headers"])).status_code == 201
    assert [n["kind"] for n in (await _bell(api, staff))["items"]] == ["team_message"]
    assert [n for n in (await _bell(api, outsider))["items"] if n["kind"] == "team_message"] == []

    # Grow: one space besides General.
    again = await api.post("/team-chat/channels", json={"name": "Ops"}, headers=admin["headers"])
    assert again.status_code == 402 and again.json()["error_code"] == "PLAN_TEAM_SPACES"

    # Members change; the outsider joins.
    members = await api.patch(f"/team-chat/channels/{space['id']}", json={"member_ids": []}, headers=admin["headers"])
    assert members.status_code == 200 and len(members.json()["member_ids"]) == 1  # the creator stays

    # Delete: the space goes, General can't.
    assert (await api.delete(f"/team-chat/channels/{general['id']}", headers=admin["headers"])).status_code == 422
    assert (await api.delete(f"/team-chat/channels/{space['id']}", headers=staff)).status_code == 404  # no longer a member
    assert (await api.delete(f"/team-chat/channels/{space['id']}", headers=admin["headers"])).status_code == 204
    assert [c["name"] for c in await _channels(api, admin["headers"])] == ["General"]
    # Room for a new one again.
    assert (await api.post("/team-chat/channels", json={"name": "Ops"}, headers=admin["headers"])).status_code == 201


@pytest.mark.asyncio
async def test_scale_has_as_many_spaces_as_it_likes(api):
    admin = await new_company(api, "Spaces Scale", plan="scale")
    for name in ("Sales", "Ops", "Finance"):
        assert (await api.post("/team-chat/channels", json={"name": name}, headers=admin["headers"])).status_code == 201
    assert len(await _channels(api, admin["headers"])) == 4


@pytest.mark.asyncio
async def test_replies_edits_reactions_files_and_mentions(api):
    admin = await new_company(api, "Chat Features")
    staff, staff_id = await _member(api, admin)
    viewer, viewer_id = await _member(api, admin, role="viewer")
    general = (await _channels(api, admin["headers"]))[0]
    url = f"/team-chat/channels/{general['id']}/messages"

    first = (await api.post(url, json={"body": "Quote for Mokoena is out"}, headers=staff)).json()
    reply = await api.post(url, json={"body": "@Lerato Dube great, chase on Friday", "reply_to_id": first["id"], "mention_ids": [viewer_id]}, headers=admin["headers"])
    assert reply.status_code == 201, reply.text
    assert reply.json()["reply_to"]["body"] == "Quote for Mokoena is out"

    # The person mentioned gets a mention; the others the usual team message.
    assert [n["kind"] for n in (await _bell(api, viewer))["items"]] == ["team_mention", "team_message"]
    assert [n["kind"] for n in (await _bell(api, staff))["items"]] == ["team_message"]

    # Edit your own; not someone else's.
    edited = await api.patch(f"/team-chat/messages/{first['id']}", json={"body": "Quote for Mokoena is out (QUO-0012)"}, headers=staff)
    assert edited.status_code == 200 and edited.json()["edited_at"]
    assert (await api.patch(f"/team-chat/messages/{first['id']}", json={"body": "x"}, headers=viewer)).status_code == 403

    # Reactions toggle.
    r = await api.post(f"/team-chat/messages/{first['id']}/reactions", json={"emoji": "👍"}, headers=viewer)
    assert r.json()["reactions"] == [{"emoji": "👍", "user_ids": [viewer_id]}]
    r = await api.post(f"/team-chat/messages/{first['id']}/reactions", json={"emoji": "👍"}, headers=viewer)
    assert r.json()["reactions"] == []
    assert (await api.post(f"/team-chat/messages/{first['id']}/reactions", json={"emoji": "💩"}, headers=viewer)).status_code == 422

    # Files: a PDF goes, a web page doesn't.
    pdf = ("quote.pdf", b"%PDF-1.4 test", "application/pdf")
    sent = await api.post(f"{url}/files", data={"body": "Signed copy"}, files=[("files", pdf)], headers=staff)
    assert sent.status_code == 201, sent.text
    (attachment,) = sent.json()["attachments"]
    assert attachment["filename"] == "quote.pdf"
    got = await api.get(f"/team-chat/messages/{sent.json()['id']}/attachments/{attachment['id']}", headers=viewer)
    assert got.status_code == 200 and got.content == b"%PDF-1.4 test" and "attachment" in got.headers["content-disposition"]
    bad = await api.post(f"{url}/files", files=[("files", ("x.html", b"<script>", "text/html"))], headers=staff)
    assert bad.status_code == 422

    # Delete: your own, or an admin anyone's; the reply survives its original.
    assert (await api.delete(f"/team-chat/messages/{first['id']}", headers=viewer)).status_code == 403
    assert (await api.delete(f"/team-chat/messages/{first['id']}", headers=admin["headers"])).status_code == 204
    messages = (await api.get(url, headers=admin["headers"])).json()
    assert [m["body"][:6] for m in messages] == ["@Lerat", "Signed"]
    assert messages[0]["reply_to"] is None


@pytest.mark.asyncio
async def test_chat_colour_is_saved_and_shared(api):
    admin = await new_company(api, "Colours")
    assert (await api.patch("/auth/me", json={"chat_color": "teal"}, headers=admin["headers"])).json()["chat_color"] == "teal"
    team = (await api.get("/team", headers=admin["headers"])).json()
    assert team[0]["chat_color"] == "teal"
    assert (await api.patch("/auth/me", json={"chat_color": "red"}, headers=admin["headers"])).status_code == 422
