# Endpoints customers reach from links in emails, with no sign-in: the
# marketing open-tracking pixel and the unsubscribe page. The random token
# in the URL is the only credential, and it can only ever opt someone out.
import base64
from html import escape

import hmac

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import UnauthorizedError
from app.core.tenancy import set_system
from app.api.routes.billing import plan_out
from app.core.plans import PLANS
from app.schemas.billing import PlanOut
from app.schemas.messaging import InboundEmail
from app.services import channel_providers as providers
from app.services import paystack
from app.core.middleware import client_ip
from app.models.platform import ContactRequest
from app.schemas.platform import ContactCreate
from app.services import platform_email
from app.services.billing_service import BillingService
from app.services.campaign_service import CampaignService
from app.services.channel_service import ChannelService, webhook_url
from app.services.messaging_service import MessagingService

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/public", tags=["public"])

_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<meta name="robots" content="noindex">
<style>body{{margin:0;background:#f4f5f7;font-family:system-ui,Arial,sans-serif;color:#1f2937}}
main{{max-width:440px;margin:12vh auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h1{{font-size:20px;margin:0 0 8px}}p{{color:#4b5563;line-height:1.5}}
button{{background:#4f46e5;color:#fff;border:0;border-radius:8px;padding:12px 20px;font-size:15px;font-weight:600;cursor:pointer}}</style>
</head><body><main>{body}</main></body></html>"""
    )


@router.get("/m/o/{token}.gif", include_in_schema=False)
async def open_pixel(token: str, db: AsyncSession = Depends(get_db)):
    set_system(db)  # the token identifies the recipient in any company
    await CampaignService(db).record_open(token)
    return Response(_PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store"})


@router.get("/m/u/{token}", response_class=HTMLResponse, include_in_schema=False)
async def unsubscribe_page(token: str):
    # A confirm button rather than unsubscribing on GET: mail scanners
    # prefetch links, and that must not opt people out by accident.
    return _page(
        "Unsubscribe",
        f"""<h1>Unsubscribe from marketing emails?</h1>
<p>You'll stop receiving news and specials. Invoices, quotes and receipts will still be sent.</p>
<form method="post" action="{escape(token)}"><button type="submit">Unsubscribe</button></form>""",
    )


@router.post("/m/u/{token}", response_class=HTMLResponse, include_in_schema=False)
async def unsubscribe(token: str, db: AsyncSession = Depends(get_db)):
    # Also the RFC 8058 one-click target (List-Unsubscribe-Post header).
    set_system(db)
    found, company = await CampaignService(db).unsubscribe(token)
    if not found:
        return _page("Unsubscribe", "<h1>Link not recognised</h1><p>This unsubscribe link is no longer valid.</p>")
    return _page(
        "Unsubscribed",
        f"<h1>You're unsubscribed</h1><p>{escape(company)} won't send you marketing emails any more.</p>",
    )


@router.post("/inbound/email", include_in_schema=False)
async def inbound_email(
    data: InboundEmail,
    x_inbound_secret: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Webhook for customer replies, posted by the mail provider's inbound
    parsing (normalised to from/to/subject/text). The shared secret proves
    the call came from our provider, not from anyone who found the URL."""
    if not hmac.compare_digest(x_inbound_secret, settings.INBOUND_EMAIL_SECRET):
        raise UnauthorizedError("Bad inbound secret")
    set_system(db)  # the address token says which company this is for
    conversation = await MessagingService(db).receive(data)
    return {"accepted": conversation is not None}


# ---------- WhatsApp / SMS (each company's own provider account) ----------
# The URL token identifies the company's connection; providers are told to
# call /public/channels/<token>/<whatsapp|sms> when they set up webhooks.


@router.get("/channels/{token}/whatsapp", include_in_schema=False)
async def whatsapp_verify(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Meta's one-time webhook check: echo hub.challenge if the verify token matches."""
    set_system(db)
    conn = await ChannelService(db).connection_for_webhook(token, "whatsapp")
    params = request.query_params
    if conn is None or params.get("hub.mode") != "subscribe" or params.get("hub.verify_token") != conn.webhook_token[:16]:
        raise UnauthorizedError("Verification failed")
    return PlainTextResponse(params.get("hub.challenge", ""))


@router.post("/channels/{token}/whatsapp", include_in_schema=False)
async def whatsapp_inbound(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    set_system(db)
    service = ChannelService(db)
    conn = await service.connection_for_webhook(token, "whatsapp")
    if conn is None:
        return {"accepted": 0}
    raw = await request.body()
    if not providers.meta_signature_ok(service.secrets_of(conn), raw, request.headers.get("X-Hub-Signature-256")):
        raise UnauthorizedError("Bad signature")
    try:
        payload = await request.json()
    except ValueError:
        return {"accepted": 0}
    # Always 200 once verified: Meta retries non-200s for days.
    return {"accepted": await service.receive_texts(conn, providers.meta_parse(payload)) if conn.enabled else 0}


@router.post("/channels/{token}/sms", include_in_schema=False)
async def sms_inbound(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    set_system(db)
    service = ChannelService(db)
    conn = await service.connection_for_webhook(token, "sms")
    if conn is None:
        return {"accepted": 0}
    if conn.provider == "twilio":
        form = dict(await request.form())
        if not providers.twilio_signature_ok(service.secrets_of(conn), webhook_url(conn), form, request.headers.get("X-Twilio-Signature")):
            raise UnauthorizedError("Bad signature")
        items = providers.twilio_parse(form)
    else:
        try:
            payload = await request.json()
        except ValueError:
            return {"accepted": 0}
        items = providers.PROVIDERS[conn.provider]["parse"](payload)
    accepted = await service.receive_texts(conn, items) if conn.enabled else 0
    if conn.provider == "twilio":
        # Twilio expects TwiML back; an empty response means "no auto-reply".
        return Response("<Response/>", media_type="text/xml")
    return {"accepted": accepted}


# ---------- Subscriptions (YGT's own Paystack account) ----------


@router.get("/plans", response_model=list[PlanOut])
async def public_plans():
    """Prices for the About page, before anyone signs in."""
    return [plan_out(p) for p in PLANS.values()]


@router.post("/paystack/webhook", include_in_schema=False)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: str | None = Header(default=None),
):
    raw = await request.body()
    if not paystack.signature_ok(raw, x_paystack_signature):
        raise UnauthorizedError("Bad signature", "PAYSTACK_SIGNATURE_INVALID")
    payload = await request.json()
    await BillingService(db).handle_event(payload.get("event", ""), payload.get("data") or {})
    return {"ok": True}



# ---------- Contact us (the public pages, before signing in) ----------


@router.post("/contact", status_code=202)
async def contact_us(data: ContactCreate, request: Request, db: AsyncSession = Depends(get_db)):
    if data.website:  # the hidden honeypot field: a bot, quietly ignored
        return {"ok": True}
    set_system(db)
    row = ContactRequest(
        name=data.name.strip(), email=data.email, phone=(data.phone or "").strip() or None, company=(data.company or "").strip() or None,
        topic=data.topic, message=data.message.strip(), ip=client_ip(request)[:64],
    )
    db.add(row)
    await db.flush()
    if settings.SUPPORT_EMAIL:
        await platform_email.queue(
            db,
            platform_email.compose(
                to=settings.SUPPORT_EMAIL,
                subject=f"Contact us ({data.topic}): {data.name}" + (f", {data.company}" if data.company else ""),
                title="New message from the website",
                paragraphs=[],
                details=[("Name", data.name), ("Email", data.email), ("Phone", data.phone or "—"), ("Company", data.company or "—"), ("Topic", data.topic.title())],
                quote=data.message,
                button=("Open in the admin site", platform_email.app_link("/admin/contact")),
                reply_to=data.email,
            ),
        )
    return {"ok": True}
