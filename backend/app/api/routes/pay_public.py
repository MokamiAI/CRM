"""The pages a customer reaches from an invoice's "Pay now" link, and the
Paystack webhook. No sign-in: the signed token in the link is the only
credential, and all it can do is pay what the invoice still owes."""
import re
from html import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.database import CommitBeforeResponseRoute
from app.core.tenancy import set_system, set_tenant
from app.models.customer import Customer
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.payment import OnlinePayment
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services import channel_providers as providers
from app.services.channel_service import ChannelService
from app.services.online_payment_service import (
    PAYABLE,
    OnlinePaymentError,
    OnlinePaymentService,
    amount_due,
    invoice_id_from,
    pay_url,
)

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/public", tags=["public"])

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

_STYLE = """body{margin:0;background:#f4f5f7;font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:#1f2937}
main{max-width:440px;margin:8vh auto;background:#fff;border-radius:14px;padding:28px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
@media (max-width:480px){main{margin:16px;padding:22px}}
.logo{max-height:48px;max-width:180px;margin-bottom:14px}
.from{font-size:13px;color:#6b7280;margin:0 0 4px}
h1{font-size:20px;margin:0 0 16px;line-height:1.3}
.amount{font-size:32px;font-weight:700;margin:4px 0 2px;letter-spacing:-.01em}
.muted{color:#6b7280;font-size:14px;line-height:1.5}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:14px;margin:16px 0 20px}
dt{color:#6b7280}dd{margin:0;text-align:right}
label{display:block;font-size:14px;font-weight:600;margin:0 0 6px}
input{width:100%;box-sizing:border-box;border:1px solid #d1d5db;border-radius:8px;padding:11px 12px;font-size:16px;margin-bottom:14px}
button,.button{display:block;width:100%;box-sizing:border-box;text-align:center;text-decoration:none;background:ACCENT;color:#fff;border:0;border-radius:10px;padding:14px 20px;font-size:16px;font-weight:600;cursor:pointer}
.secure{font-size:12px;color:#6b7280;text-align:center;margin:12px 0 0}
.ok{color:#047857}.warn{color:#b45309}"""


def _page(title: str, body: str, company=None, accent: str = "#4f46e5") -> HTMLResponse:
    logo = f'<img class="logo" src="{escape(company.logo_url)}" alt="">' if company is not None and company.logo_url else ""
    sender = f'<p class="from">{escape(company.company_name)}</p>' if company is not None else ""
    response = HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<meta name="robots" content="noindex"><style>{_STYLE.replace("ACCENT", escape(accent))}</style>
</head><body><main>{logo}{sender}{body}</main></body></html>"""
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _money(company, amount) -> str:
    return f"{escape(company.default_currency or 'ZAR')} {amount:,.2f}"


async def _load(db: AsyncSession, token: str):
    """The invoice, its customer and company, acting as that company; or
    None if the link isn't one of ours."""
    invoice_id = invoice_id_from(token)
    if invoice_id is None:
        return None
    set_system(db)
    company_id = await db.scalar(select(Invoice.company_id).where(Invoice.id == invoice_id))
    if company_id is None:
        return None
    set_tenant(db, company_id)
    invoice = await db.get(Invoice, invoice_id)
    customer = await db.get(Customer, invoice.customer_id)
    company = await CompanySettingsRepository(db).get_current()
    return invoice, customer, company


def _accent(company) -> str:
    from app.schemas.documents import resolve_template

    try:
        return resolve_template(company).accent or "#4f46e5"
    except Exception:
        return "#4f46e5"


_NOT_FOUND = ("Link not recognised", "<h1>Link not recognised</h1><p class='muted'>This payment link isn't valid. Please use the link in the latest email from the business.</p>")


def _closed(invoice, company) -> HTMLResponse | None:
    """The page for an invoice that can't be paid online now, if it can't."""
    accent = _accent(company)
    if invoice.status == InvoiceStatus.PAID or (invoice.status in PAYABLE and amount_due(invoice) <= 0):
        return _page("Paid", f"<h1 class='ok'>Invoice {escape(invoice.invoice_number)} is paid</h1><p class='muted'>There is nothing left to pay. Thank you.</p>", company, accent)
    if invoice.status == InvoiceStatus.VOID:
        return _page("Cancelled", f"<h1>Invoice {escape(invoice.invoice_number)} was cancelled</h1><p class='muted'>It doesn't need to be paid. Please contact {escape(company.company_name)} if you have questions.</p>", company, accent)
    if invoice.status not in PAYABLE:
        return _page("Not available", "<h1>This invoice can't be paid yet</h1><p class='muted'>Please use the link in the email you received with the invoice.</p>", company, accent)
    return None


def _form(invoice, customer, company, error: str | None = None) -> HTMLResponse:
    due = amount_due(invoice)
    ask_email = not (customer and customer.recipient_email)
    email_box = (
        '<label for="email">Your email, for the receipt</label><input id="email" name="email" type="email" required autocomplete="email">'
        if ask_email
        else ""
    )
    paid_line = f"<dt>Already paid</dt><dd>{_money(company, invoice.amount_paid)}</dd>" if invoice.amount_paid and invoice.amount_paid > 0 else ""
    error_line = f"<p class='warn'>{escape(error)}</p>" if error else ""
    body = f"""<h1>Pay invoice {escape(invoice.invoice_number)}</h1>
<p class="muted" style="margin:0">Amount due</p><p class="amount">{_money(company, due)}</p>
<dl><dt>Invoice</dt><dd>{escape(invoice.invoice_number)}</dd><dt>Due date</dt><dd>{invoice.due_date:%d %b %Y}</dd>
<dt>Invoice total</dt><dd>{_money(company, invoice.total)}</dd>{paid_line}</dl>
{error_line}<form method="post" onsubmit="var b=this.querySelector('button');b.disabled=true;b.textContent='Opening Paystack…'">{email_box}<button type="submit">Pay {_money(company, due)}</button></form>
<p class="secure">You'll pay securely on Paystack. {escape(company.company_name)} receives the payment directly.</p>"""
    return _page(f"Pay invoice {invoice.invoice_number}", body, company, _accent(company))


@router.get("/pay/{token}", response_class=HTMLResponse, include_in_schema=False)
async def pay_page(token: str, db: AsyncSession = Depends(get_db)):
    # A button, never a redirect on GET: mail scanners open links, and that
    # must not start payments.
    loaded = await _load(db, token)
    if loaded is None:
        return _page(*_NOT_FOUND)
    invoice, customer, company = loaded
    if (closed := _closed(invoice, company)) is not None:
        return closed
    if await OnlinePaymentService(db).connection() is None:
        return _page(
            "Pay by EFT",
            f"<h1>Online payment isn't available</h1><p class='muted'>Please pay invoice {escape(invoice.invoice_number)} by EFT using the banking details on the invoice.</p>",
            company,
            _accent(company),
        )
    return _form(invoice, customer, company)


@router.post("/pay/{token}", include_in_schema=False)
async def start_payment(token: str, email: str | None = Form(default=None), db: AsyncSession = Depends(get_db)):
    loaded = await _load(db, token)
    if loaded is None:
        return _page(*_NOT_FOUND)
    invoice, customer, company = loaded
    if (closed := _closed(invoice, company)) is not None:
        return closed
    typed = (email or "").strip()
    if not (customer and customer.recipient_email) and typed and not _EMAIL.fullmatch(typed):
        return _form(invoice, customer, company, error="Please check your email address.")
    payer = (customer.recipient_email if customer else None) or typed or None
    try:
        checkout = await OnlinePaymentService(db).start(invoice, payer, return_url=f"{pay_url(invoice.id)}/done", cancel_url=pay_url(invoice.id))
    except OnlinePaymentError as exc:
        await db.commit()  # keep the failed attempt on record
        return _form(invoice, customer, company, error=exc.message)
    await db.commit()
    return RedirectResponse(checkout, status_code=303)


@router.get("/pay/{token}/done", response_class=HTMLResponse, include_in_schema=False)
async def payment_done(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Where Paystack sends the customer back to, with ?reference=."""
    loaded = await _load(db, token)
    if loaded is None:
        return _page(*_NOT_FOUND)
    invoice, customer, company = loaded
    reference = request.query_params.get("reference") or request.query_params.get("trxref") or ""
    attempt = await db.scalar(select(OnlinePayment).where(OnlinePayment.reference == reference, OnlinePayment.invoice_id == invoice.id))
    accent = _accent(company)
    if attempt is None:
        return _page("Payment", "<h1>We couldn't find that payment</h1><p class='muted'>If money left your account, the business will see it. Otherwise, please try again.</p>"
                     f"<a class='button' href='{escape(pay_url(invoice.id))}'>Back to the invoice</a>", company, accent)
    attempt = await OnlinePaymentService(db).settle(reference)
    await db.commit()
    if attempt.status in ("paid", "needs_attention"):
        await db.refresh(invoice)
        left = amount_due(invoice)
        still = f"<p class='muted'>{_money(company, left)} is still owed on this invoice.</p>" if attempt.status == "paid" and left > 0 else ""
        return _page(
            "Thank you",
            f"<h1 class='ok'>Thank you, your payment went through</h1><p class='amount'>{_money(company, attempt.amount)}</p>"
            f"<p class='muted'>Paid on invoice {escape(invoice.invoice_number)}. {escape(company.company_name)} has been told, and a receipt is on its way to your email.</p>{still}",
            company,
            accent,
        )
    if attempt.status == "pending":
        return _page(
            "Waiting for confirmation",
            "<h1>Waiting for Paystack to confirm</h1><p class='muted'>If you paid, this can take a minute: refresh this page shortly, and you'll also get a receipt by email. "
            "If you didn't finish paying, no money was taken.</p>"
            f"<a class='button' href=''>Refresh</a><p class='secure'><a href='{escape(pay_url(invoice.id))}'>Didn't finish? Try again</a></p>",
            company,
            accent,
        )
    return _page(
        "Payment not completed",
        "<h1 class='warn'>The payment didn't go through</h1><p class='muted'>No money was taken. You can try again, or pay by EFT using the banking details on the invoice.</p>"
        f"<a class='button' href='{escape(pay_url(invoice.id))}'>Try again</a>",
        company,
        accent,
    )


@router.post("/channels/{token}/payments", include_in_schema=False)
async def paystack_webhook(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Optional: the company pastes this URL into Paystack > Settings >
    API Keys & Webhooks, so payments show up within seconds."""
    set_system(db)
    service = ChannelService(db)
    conn = await service.connection_for_webhook(token, "payments")  # scopes the session to its company
    if conn is None:
        return {"accepted": 0}
    raw = await request.body()
    if not providers.paystack_signature_ok(service.secrets_of(conn), raw, request.headers.get("x-paystack-signature")):
        return {"accepted": 0}
    try:
        event = await request.json()
    except ValueError:
        return {"accepted": 0}
    reference = ((event.get("data") or {}).get("reference") or "") if event.get("event") == "charge.success" else ""
    # Charges that aren't ours (their online shop, say) are ignored. Always
    # 200: Paystack retries anything else for days.
    if not reference or await db.scalar(select(OnlinePayment.id).where(OnlinePayment.reference == reference)) is None:
        return {"accepted": 0}
    attempt = await OnlinePaymentService(db).settle(reference)
    await db.commit()
    return {"accepted": int(attempt is not None and attempt.status == "paid")}
