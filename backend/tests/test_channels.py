import base64
import hashlib
import hmac

from app.core.crypto import decrypt, decrypt_json, encrypt, encrypt_json
from app.services import channel_providers as p


def test_normalize_phone_south_african_formats():
    assert p.normalize_phone("082 123 4567") == "27821234567"
    assert p.normalize_phone("+27 82 123 4567") == "27821234567"
    assert p.normalize_phone("0027821234567") == "27821234567"
    assert p.normalize_phone("27821234567") == "27821234567"
    assert p.normalize_phone("123") is None
    assert p.normalize_phone(None) is None


def test_secrets_are_encrypted_and_round_trip():
    token = encrypt("s3cret!")
    assert token != "s3cret!" and token.startswith("gAAAA")
    assert decrypt(token) == "s3cret!"
    assert decrypt("legacy-plain") == "legacy-plain"  # saved before encryption
    blob = encrypt_json({"access_token": "abc"})
    assert "abc" not in blob and decrypt_json(blob) == {"access_token": "abc"}
    assert decrypt_json("not-a-token") == {}


def test_meta_webhook_parsing():
    payload = {
        "entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": "27821234567", "profile": {"name": "Johan"}}],
            "messages": [
                {"from": "27821234567", "id": "wamid.1", "type": "text", "text": {"body": "Hi there"}},
                {"from": "27821234567", "id": "wamid.2", "type": "image", "image": {}},
            ],
        }}]}]
    }
    first, second = p.meta_parse(payload)
    assert (first.from_phone, first.text, first.name, first.external_id) == ("27821234567", "Hi there", "Johan", "wamid.1")
    assert second.text.startswith("[image received")
    assert p.meta_parse({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []  # delivery receipts


def test_meta_signature():
    body = b'{"entry":[]}'
    good = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert p.meta_signature_ok({"app_secret": "appsecret"}, body, good)
    assert not p.meta_signature_ok({"app_secret": "appsecret"}, body, "sha256=bad")
    assert p.meta_signature_ok({}, body, None)  # optional when no app secret saved


def test_twilio_signature_and_parse():
    url, form = "https://crm.example.com/api/v1/public/channels/tok/sms", {"From": "+27821234567", "Body": "Yes", "MessageSid": "SM1"}
    data = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    sig = base64.b64encode(hmac.new(b"authtoken", data.encode(), hashlib.sha1).digest()).decode()
    assert p.twilio_signature_ok({"auth_token": "authtoken"}, url, form, sig)
    assert not p.twilio_signature_ok({"auth_token": "authtoken"}, url, form, "nope")
    [msg] = p.twilio_parse(form)
    assert (msg.from_phone, msg.text, msg.external_id) == ("+27821234567", "Yes", "SM1")


def test_bulksms_and_clickatell_parse():
    [b] = p.bulksms_parse([{"id": "1", "from": "27821234567", "body": "Stop"}])
    assert (b.from_phone, b.text) == ("27821234567", "Stop")
    [c] = p.clickatell_parse({"fromNumber": "27821234567", "text": "OK", "messageId": "m1"})
    assert (c.from_phone, c.text, c.external_id) == ("27821234567", "OK", "m1")
    assert p.clickatell_parse({}) == []


def test_override_routes_provider_calls_to_a_mock(monkeypatch):
    monkeypatch.setattr(p.settings, "CHANNEL_API_OVERRIDE", "http://127.0.0.1:9100")
    assert p._url("https://api.bulksms.com/v1/messages") == "http://127.0.0.1:9100/api.bulksms.com/v1/messages"
    monkeypatch.setattr(p.settings, "CHANNEL_API_OVERRIDE", None)
    assert p._url("https://api.bulksms.com/v1/messages") == "https://api.bulksms.com/v1/messages"
