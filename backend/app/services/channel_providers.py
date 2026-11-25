"""WhatsApp, SMS and online payment providers a company can connect in Settings.

Each provider declares the fields its settings form needs (plain vs
secret), how to test the credentials, how to send a text, and how to read
the messages it posts to our webhook. Credentials are always the
company's own; nothing here is configured on the server.
"""
import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

_TIMEOUT = httpx.Timeout(20.0)


class ProviderError(Exception):
    """A provider rejected a call; the message is safe to show the admin."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    secret: bool = False
    required: bool = True


@dataclass
class InboundText:
    from_phone: str
    text: str
    name: str | None = None
    external_id: str | None = None


@dataclass
class ProviderSpec:
    kind: str  # whatsapp | sms
    fields: list[FieldSpec] = field(default_factory=list)

    @property
    def secret_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.secret]


def normalize_phone(raw: str | None, default_country: str | None = "27") -> str | None:
    """International digits without '+', e.g. '082 123 4567' -> '27821234567'.
    Local numbers starting with 0 get the company's dialling code (see
    company_dial); with none ("another country") they need a +code."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        if not default_country:
            return None
        digits = default_country + digits[1:]
    return digits if 8 <= len(digits) <= 15 else None


def company_dial(company) -> str:
    """The dialling code for a company's local numbers: '27', '254', ''."""
    from app.core.countries import country

    return country(getattr(company, "country", None)).dial


def _url(real: str) -> str:
    """Real provider URL, or the same path on the test mock when configured."""
    override = settings.CHANNEL_API_OVERRIDE
    if not override:
        return real
    parts = urlsplit(real)
    return f"{override.rstrip('/')}/{parts.netloc}{parts.path}" + (f"?{parts.query}" if parts.query else "")


async def _request(method: str, url: str, **kwargs) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(method, _url(url), **kwargs)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Could not reach the provider: {exc.__class__.__name__}") from exc
    if response.status_code >= 400:
        raise ProviderError(_error_text(response))
    return response


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    # Meta: {"error": {"message": ...}}; BulkSMS: {"detail": ...}; Twilio: {"message": ...}
    message = (
        (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else None
    ) or body.get("detail") or body.get("message") or body.get("error") or str(body)[:200]
    return f"HTTP {response.status_code}: {message}"


# ---------------------------------------------------------------- WhatsApp


# Meta retires each Graph API version about two years after release (v21.0
# stops on 21 Jan 2027). v26.0 came out in July 2026.
GRAPH = "https://graph.facebook.com/v26.0"

META_WHATSAPP = ProviderSpec(
    kind="whatsapp",
    fields=[
        FieldSpec("phone_number_id"),
        FieldSpec("business_account_id", required=False),
        FieldSpec("access_token", secret=True),
        # Optional: lets us verify each webhook call really came from Meta.
        FieldSpec("app_secret", secret=True, required=False),
        # Also send payment reminders on WhatsApp (an approved template).
        FieldSpec("payment_reminders", required=False),
    ],
)


async def meta_test(cfg: dict, secrets: dict) -> str:
    response = await _request(
        "GET",
        f"{GRAPH}/{cfg['phone_number_id']}",
        params={"fields": "display_phone_number,verified_name"},
        headers={"Authorization": f"Bearer {secrets['access_token']}"},
    )
    data = response.json()
    return f"{data.get('verified_name', '')} {data.get('display_phone_number', '')}".strip() or "Connected"


async def meta_send(cfg: dict, secrets: dict, to: str, body: str) -> str | None:
    response = await _request(
        "POST",
        f"{GRAPH}/{cfg['phone_number_id']}/messages",
        headers={"Authorization": f"Bearer {secrets['access_token']}"},
        json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "text", "text": {"preview_url": False, "body": body}},
    )
    messages = response.json().get("messages") or [{}]
    return messages[0].get("id")


async def meta_register(cfg: dict, secrets: dict, pin: str) -> None:
    """Registers the number for the Cloud API, setting its two-step PIN. A
    number added in WhatsApp Manager stays "Pending" until this is done."""
    await _request(
        "POST",
        f"{GRAPH}/{cfg['phone_number_id']}/register",
        headers={"Authorization": f"Bearer {secrets['access_token']}"},
        json={"messaging_product": "whatsapp", "pin": pin},
    )


async def meta_create_template(cfg: dict, secrets: dict, template: dict) -> str:
    """Submits a message template to Meta for approval; returns its status.
    One that already exists under this name is left as it is."""
    try:
        response = await _request(
            "POST",
            f"{GRAPH}/{cfg['business_account_id']}/message_templates",
            headers={"Authorization": f"Bearer {secrets['access_token']}"},
            json=template,
        )
    except ProviderError as exc:
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            return "EXISTS"
        raise
    return (response.json().get("status") or "PENDING").upper()


async def meta_template_statuses(cfg: dict, secrets: dict) -> dict[str, str]:
    """name -> APPROVED / PENDING / REJECTED / PAUSED / DISABLED."""
    response = await _request(
        "GET",
        f"{GRAPH}/{cfg['business_account_id']}/message_templates",
        headers={"Authorization": f"Bearer {secrets['access_token']}"},
        params={"fields": "name,status,language", "limit": 200},
    )
    return {t["name"]: (t.get("status") or "").upper() for t in response.json().get("data", []) if t.get("name")}


async def meta_send_template(cfg: dict, secrets: dict, to: str, name: str, language: str, body: list[str], button: str | None = None) -> str | None:
    """Sends an approved template: the only kind of message Meta allows
    more than 24 hours after the customer last wrote."""
    components = [{"type": "body", "parameters": [{"type": "text", "text": value} for value in body]}]
    if button is not None:
        components.append({"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": button}]})
    response = await _request(
        "POST",
        f"{GRAPH}/{cfg['phone_number_id']}/messages",
        headers={"Authorization": f"Bearer {secrets['access_token']}"},
        json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "template",
              "template": {"name": name, "language": {"code": language}, "components": components}},
    )
    messages = response.json().get("messages") or [{}]
    return messages[0].get("id")


def meta_parse(payload: dict) -> list[InboundText]:
    out: list[InboundText] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                text = (m.get("text") or {}).get("body") or (m.get("button") or {}).get("text")
                if not text:
                    kind = m.get("type", "message")
                    text = f"[{kind} received: open WhatsApp to view]"
                out.append(InboundText(from_phone=m.get("from", ""), text=text, name=names.get(m.get("from")), external_id=m.get("id")))
    return out


def meta_signature_ok(secrets: dict, raw_body: bytes, header: str | None) -> bool:
    app_secret = secrets.get("app_secret")
    if not app_secret:
        return True  # optional; the unguessable webhook URL still protects it
    expected = "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return bool(header) and hmac.compare_digest(expected, header)


# ---------------------------------------------------------------- SMS

BULKSMS = ProviderSpec(
    kind="sms",
    fields=[FieldSpec("token_id"), FieldSpec("token_secret", secret=True), FieldSpec("sender", required=False)],
)
CLICKATELL = ProviderSpec(
    kind="sms",
    fields=[FieldSpec("api_key", secret=True), FieldSpec("sender", required=False)],
)
TWILIO = ProviderSpec(
    kind="sms",
    fields=[FieldSpec("account_sid"), FieldSpec("auth_token", secret=True), FieldSpec("sender")],
)


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


async def bulksms_test(cfg: dict, secrets: dict) -> str:
    response = await _request("GET", "https://api.bulksms.com/v1/profile", headers={"Authorization": _basic(cfg["token_id"], secrets["token_secret"])})
    credits = (response.json().get("credits") or {}).get("balance")
    return f"Connected. Credit balance: {credits}" if credits is not None else "Connected"


async def bulksms_send(cfg: dict, secrets: dict, to: str, body: str) -> str | None:
    message = {"to": f"+{to}", "body": body}
    if cfg.get("sender"):
        message["from"] = cfg["sender"]
    response = await _request(
        "POST",
        "https://api.bulksms.com/v1/messages",
        headers={"Authorization": _basic(cfg["token_id"], secrets["token_secret"])},
        json=[message],
    )
    data = response.json()
    return (data[0] if isinstance(data, list) and data else {}).get("id")


def bulksms_parse(payload) -> list[InboundText]:
    items = payload if isinstance(payload, list) else [payload]
    return [InboundText(from_phone=str(m.get("from", "")), text=m.get("body", ""), external_id=m.get("id")) for m in items if isinstance(m, dict) and m.get("body")]


async def clickatell_test(cfg: dict, secrets: dict) -> str:
    # Clickatell has no cheap "who am I" call; the admin sends a test SMS instead.
    raise ProviderError("Enter a phone number below to send a test SMS")


async def clickatell_send(cfg: dict, secrets: dict, to: str, body: str) -> str | None:
    message = {"channel": "sms", "to": to, "content": body}
    if cfg.get("sender"):
        message["from"] = cfg["sender"]
    response = await _request(
        "POST",
        "https://platform.clickatell.com/v1/message",
        headers={"Authorization": secrets["api_key"]},
        json={"messages": [message]},
    )
    messages = response.json().get("messages") or [{}]
    if messages[0].get("error"):
        raise ProviderError(str(messages[0]["error"]))
    return messages[0].get("apiMessageId")


def clickatell_parse(payload: dict) -> list[InboundText]:
    if not isinstance(payload, dict) or not payload.get("text"):
        return []
    return [InboundText(from_phone=str(payload.get("fromNumber", "")), text=payload["text"], external_id=payload.get("messageId"))]


async def twilio_test(cfg: dict, secrets: dict) -> str:
    response = await _request(
        "GET",
        f"https://api.twilio.com/2010-04-01/Accounts/{cfg['account_sid']}.json",
        headers={"Authorization": _basic(cfg["account_sid"], secrets["auth_token"])},
    )
    return f"Connected: {response.json().get('friendly_name', cfg['account_sid'])}"


async def twilio_send(cfg: dict, secrets: dict, to: str, body: str) -> str | None:
    response = await _request(
        "POST",
        f"https://api.twilio.com/2010-04-01/Accounts/{cfg['account_sid']}/Messages.json",
        headers={"Authorization": _basic(cfg["account_sid"], secrets["auth_token"])},
        data={"To": f"+{to}", "From": cfg["sender"], "Body": body},
    )
    return response.json().get("sid")


def twilio_parse(form: dict) -> list[InboundText]:
    if not form.get("Body") and not form.get("From"):
        return []
    return [InboundText(from_phone=str(form.get("From", "")), text=form.get("Body", ""), external_id=form.get("MessageSid"))]


def twilio_signature_ok(secrets: dict, url: str, form: dict, header: str | None) -> bool:
    """Twilio signs url + sorted form params with the auth token (HMAC-SHA1)."""
    data = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    expected = base64.b64encode(hmac.new(secrets["auth_token"].encode(), data.encode(), hashlib.sha1).digest()).decode()
    return bool(header) and hmac.compare_digest(expected, header)


# ---------------------------------------------------------------- Online payments
# The company's own Paystack account: customers pay invoices into it, and
# YGT only starts each payment and reads back whether it went through.
# (YGT's subscription billing uses the platform's key, in paystack.py.)

PAYSTACK = ProviderSpec(kind="payments", fields=[FieldSpec("secret_key", secret=True)])


def _paystack_key(secrets: dict) -> str:
    key = (secrets.get("secret_key") or "").strip()
    if key.startswith("pk_"):
        raise ProviderError("That is the public key. Paste the secret key (it starts with sk_live_ or sk_test_).")
    if not key.startswith(("sk_live_", "sk_test_")):
        raise ProviderError("A Paystack secret key starts with sk_live_ or sk_test_.")
    return key


async def _paystack(method: str, path: str, secrets: dict, **kwargs) -> dict:
    response = await _request(
        method, f"{settings.PAYSTACK_API_BASE.rstrip('/')}{path}", headers={"Authorization": f"Bearer {_paystack_key(secrets)}"}, **kwargs
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise ProviderError(f"Paystack returned HTTP {response.status_code}") from exc
    if not body.get("status"):
        raise ProviderError(f"Paystack: {body.get('message') or 'request refused'}")
    return body.get("data") or {}


def paystack_test_mode(secrets: dict) -> bool:
    return (secrets.get("secret_key") or "").strip().startswith("sk_test_")


async def paystack_test(cfg: dict, secrets: dict) -> str:
    # Any call needs a valid secret key; the balance endpoint changes nothing.
    await _paystack("GET", "/balance", secrets)
    if paystack_test_mode(secrets):
        return "Connected to Paystack in test mode: no real money moves. Use your live secret key when you're ready."
    return "Connected to Paystack. Customers can now pay your invoices online."


async def paystack_start(secrets: dict, *, email: str, amount_cents: int, currency: str, reference: str, callback_url: str, metadata: dict) -> str:
    """Opens a Paystack checkout for one payment; returns its page."""
    data = await _paystack(
        "POST",
        "/transaction/initialize",
        secrets,
        json={"email": email, "amount": amount_cents, "currency": currency, "reference": reference, "callback_url": callback_url, "metadata": metadata},
    )
    return data["authorization_url"]


async def paystack_verify(secrets: dict, reference: str) -> dict:
    return await _paystack("GET", f"/transaction/verify/{reference}", secrets)


def paystack_signature_ok(secrets: dict, raw_body: bytes, header: str | None) -> bool:
    """Paystack signs each webhook with HMAC-SHA512 of the body, keyed by the
    account's secret key, in the x-paystack-signature header."""
    key = (secrets.get("secret_key") or "").strip()
    if not key or not header:
        return False
    expected = hmac.new(key.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, header)


PROVIDERS: dict[str, dict] = {
    "meta": {"spec": META_WHATSAPP, "test": meta_test, "send": meta_send, "parse": meta_parse},
    "bulksms": {"spec": BULKSMS, "test": bulksms_test, "send": bulksms_send, "parse": bulksms_parse},
    "clickatell": {"spec": CLICKATELL, "test": clickatell_test, "send": clickatell_send, "parse": clickatell_parse},
    "twilio": {"spec": TWILIO, "test": twilio_test, "send": twilio_send, "parse": twilio_parse},
    "paystack": {"spec": PAYSTACK, "test": paystack_test},
}
PROVIDERS_FOR = {"whatsapp": ["meta"], "sms": ["bulksms", "clickatell", "twilio"], "payments": ["paystack"]}
