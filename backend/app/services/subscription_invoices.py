"""YGT's own invoices to its subscribers: one per subscription payment,
issued the moment Paystack confirms the payment, numbered YGT-INV-000001
upwards, and emailed to the company's admins.

YGT's details (legal name, address, registration and VAT number) are
edited in the YGT admin site, never hard-coded. Until a VAT number is set
the invoice is a plain "Invoice" with no VAT; once it is, new invoices are
"Tax invoices" with the VAT inside the price shown separately. Invoices
already issued keep the details they were issued with."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plans import PLANS
from app.models.billing import BillingPayment, SubscriptionInvoice
from app.models.company_settings import CompanySettings
from app.models.enums import UserRole
from app.models.platform import PlatformSetting
from app.models.user import User
from app.schemas.documents import DocumentTemplate

logger = logging.getLogger(__name__)

DETAILS_KEY = "ygt_details"
COUNTER_KEY = "subscription_invoice_counter"
VAT_RATE = Decimal("15")
DEFAULT_DETAILS = {
    "legal_name": "YGT",
    "address": None,
    "registration_number": None,
    "vat_number": None,
    "email": None,
    "phone": None,
    "website": "yougt.co.za",
    "bank_name": None,
    "account_holder": None,
    "account_number": None,
    "branch_code": None,
    "account_type": None,
}


async def get_details(db: AsyncSession) -> dict:
    row = await db.get(PlatformSetting, DETAILS_KEY)
    return {**DEFAULT_DETAILS, **(row.value if row else {})}


async def save_details(db: AsyncSession, values: dict) -> dict:
    clean = {k: (str(v).strip() or None) if v is not None else None for k, v in values.items() if k in DEFAULT_DETAILS}
    row = await db.get(PlatformSetting, DETAILS_KEY)
    if row is None:
        db.add(PlatformSetting(key=DETAILS_KEY, value=clean))
    else:
        row.value = clean
    await db.flush()
    return {**DEFAULT_DETAILS, **clean}


async def _next_number(db: AsyncSession) -> str:
    """The next invoice number. The counter row is locked until the
    transaction ends, so two payments at once never share a number."""
    await db.execute(insert(PlatformSetting).values(key=COUNTER_KEY, value={"last": 0}).on_conflict_do_nothing(index_elements=["key"]))
    row = await db.scalar(select(PlatformSetting).where(PlatformSetting.key == COUNTER_KEY).with_for_update())
    last = int(row.value.get("last", 0)) + 1
    row.value = {"last": last}
    return f"YGT-INV-{last:06d}"


def _vat_inside(amount_cents: int) -> int:
    """VAT contained in a VAT-inclusive amount, at 15%."""
    vat = Decimal(amount_cents) * VAT_RATE / (Decimal(100) + VAT_RATE)
    return int(vat.quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def issue_for_payment(db: AsyncSession, payment: BillingPayment, period_end: datetime | None) -> SubscriptionInvoice | None:
    """Makes the invoice for a payment (once: a second call returns None)."""
    if await db.scalar(select(SubscriptionInvoice.id).where(SubscriptionInvoice.payment_id == payment.id)):
        return None
    seller = await get_details(db)
    company = await db.get(CompanySettings, payment.company_id)
    buyer = {
        "name": company.company_name if company else "",
        "address": company.address if company else None,
        "vat_number": company.tax_number if company and company.vat_registered else None,
    }
    vat = _vat_inside(payment.amount_cents) if seller.get("vat_number") else 0
    invoice = SubscriptionInvoice(
        company_id=payment.company_id,
        number=await _next_number(db),
        payment_id=payment.id,
        payment_reference=payment.reference,
        issued_at=payment.paid_at,
        plan=payment.plan,
        interval=payment.interval,
        seats=payment.seats,
        period_start=payment.paid_at,
        period_end=period_end or payment.paid_at,
        amount_cents=payment.amount_cents,
        vat_cents=vat,
        seller=seller,
        buyer=buyer,
    )
    db.add(invoice)
    await db.flush()
    return invoice


async def recipients(db: AsyncSession, company_id: uuid.UUID, billing_email: str | None) -> list[str]:
    admins = await db.scalars(
        select(User.email).where(User.company_id == company_id, User.role == UserRole.ADMIN, User.is_active.is_(True))
    )
    emails = {e.lower() for e in admins.all() if e}
    if billing_email:
        emails.add(billing_email.lower())
    return sorted(emails)


def plan_label(invoice: SubscriptionInvoice) -> str:
    plan = PLANS.get(invoice.plan)
    name = plan.name if plan else invoice.plan.title()
    per = "year" if invoice.interval == "annually" else "month"
    seats = f", {invoice.seats} seat{'s' if invoice.seats != 1 else ''}" if plan and plan.per_user else ""
    return f"YGT {name} plan, 1 {per}{seats}"


def render_html(invoice: SubscriptionInvoice) -> str:
    """The invoice as a printable page, in the same layout as a company's
    own documents."""
    from app.services.document_service import render

    s = invoice.seller or {}
    vat_vendor = bool(s.get("vat_number"))
    total = Decimal(invoice.amount_cents) / 100
    vat = Decimal(invoice.vat_cents) / 100
    company = SimpleNamespace(
        company_name=s.get("legal_name") or "YGT", address=s.get("address"), tax_number=s.get("vat_number"),
        sender_email=s.get("email"), logo_url=None, default_currency="ZAR",
    )
    template = DocumentTemplate(
        invoice_title="Tax invoice" if vat_vendor else "Invoice",
        registration_number=s.get("registration_number"), phone=s.get("phone"), website=s.get("website"),
        bank_name=s.get("bank_name"), account_holder=s.get("account_holder"),
        account_number=s.get("account_number"), branch_code=s.get("branch_code"), account_type=s.get("account_type"),
        payment_reference=invoice.payment_reference, accent="#2563eb",
    )
    b = invoice.buyer or {}
    customer = SimpleNamespace(name=b.get("name"), billing_address=b.get("address"), email=None, phone=None, tax_number=b.get("vat_number"))
    item = SimpleNamespace(description=plan_label(invoice), quantity=Decimal(1), unit_price=total - vat, tax_rate=VAT_RATE if vat_vendor else Decimal(0), line_total=total - vat)
    doc = SimpleNamespace(items=[item], subtotal=total - vat, tax_total=vat, total=total)
    return render("subscription_invoice", company, template, doc=doc, customer=customer, invoice=invoice, vat_vendor=vat_vendor)


def email_for(invoice: SubscriptionInvoice, to: str, paid_on: datetime | None = None):
    from app.services import platform_email

    total = f"R {Decimal(invoice.amount_cents) / 100:,.2f}".replace(",", " ")
    return platform_email.compose(
        to=to,
        subject=f"Your YGT invoice {invoice.number}: paid, thank you",
        title=f"Thank you: payment received ({invoice.number})",
        paragraphs=[
            f"We've received your payment of {total} for your YGT subscription, and your plan is active.",
            "Your invoice is in YGT under Settings > Billing, ready to view, print or save as PDF.",
        ],
        details=[
            ("Invoice", invoice.number),
            ("Plan", plan_label(invoice)),
            ("Amount paid", total),
            ("Payment reference", invoice.payment_reference),
            ("Paid on", (paid_on or invoice.issued_at).strftime("%d %b %Y")),
        ],
        button=("View invoice", platform_email.app_link("/settings?tab=billing")),
    )
