"""Customers paying invoices online, into the company's own Paystack account.

The pay link on an invoice (email, PDF, reminders) opens a YGT page, not
Paystack directly. Only when the customer presses "Pay" does YGT work out
what is still owed at that moment and open a Paystack checkout for exactly
that: an invoice paid in part by EFT is charged only the rest, and a paid
or cancelled one takes no money at all. The amount never comes from the
link, so it can't be changed.

A payment is confirmed three ways, whichever comes first: the customer
returning from Paystack, Paystack's webhook (if the owner set it up), and
a check every few minutes. Each confirmation asks Paystack itself, and a
Paystack reference is recorded once, so a payment is never missed and
never counted twice. YGT never holds the money.
"""
import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import status
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError
from app.models.enums import InvoiceStatus, PaymentMethod, UserRole
from app.models.invoice import Invoice
from app.models.messaging import ChannelConnection
from app.models.payment import OnlinePayment
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.payment import PaymentCreate
from app.services import channel_providers as providers
from app.services.channel_providers import ProviderError
from app.services.channel_service import ChannelService
from app.services.notify import notify
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

# Invoices a customer can still pay. DRAFT hasn't been sent yet.
PAYABLE = {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE}
# A checkout nobody finished is given up on after this long. The return
# page and the webhook still confirm it if the customer pays later.
GIVE_UP_AFTER = timedelta(hours=2)
_METHODS = {"card": PaymentMethod.CARD, "eft": PaymentMethod.EFT, "bank_transfer": PaymentMethod.EFT, "bank": PaymentMethod.EFT}


class OnlinePaymentError(AppError):
    """Shown to the customer on the pay page."""

    def __init__(self, message: str, code: str = "ONLINE_PAYMENT_UNAVAILABLE"):
        super().__init__(message, code, status.HTTP_409_CONFLICT)


# ---------- The pay link ----------
# The invoice id plus a signature: short enough for a QR code on a printed
# invoice, can't be guessed or altered, and never expires (it only ever
# charges what is still owed).


def _signature(invoice_id: uuid.UUID) -> str:
    digest = hmac.new(settings.JWT_SECRET.encode(), f"invoice-pay:{invoice_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode()[:22]


def pay_token(invoice_id: uuid.UUID) -> str:
    return f"{invoice_id.hex}{_signature(invoice_id)}"


def invoice_id_from(token: str) -> uuid.UUID | None:
    try:
        invoice_id = uuid.UUID(hex=token[:32])
    except (ValueError, TypeError):
        return None
    return invoice_id if hmac.compare_digest(token[32:], _signature(invoice_id)) else None


def pay_url(invoice_id: uuid.UUID) -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/pay/{pay_token(invoice_id)}"


def amount_due(invoice: Invoice) -> Decimal:
    return Decimal(invoice.amount_due)


def _cents(amount) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def _paid_at(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _money(currency: str, amount) -> str:
    return f"{currency} {Decimal(amount):,.2f}"


class OnlinePaymentService:
    """Acts for one company: the session must be scoped to it."""

    def __init__(self, db):
        self.db = db
        self.channels = ChannelService(db)

    async def connection(self) -> ChannelConnection | None:
        return await self.channels.enabled("payments")

    async def pay_url_for(self, invoice: Invoice) -> str | None:
        """The link to print and email, or None if online payment isn't
        switched on or there is nothing left to pay."""
        if invoice.status not in PAYABLE or amount_due(invoice) <= 0:
            return None
        return pay_url(invoice.id) if await self.connection() else None

    async def start(self, invoice: Invoice, payer_email: str | None, return_url: str, cancel_url: str | None = None) -> str:
        """Opens a checkout for what is owed right now; returns its page."""
        conn = await self.connection()
        if conn is None:
            raise OnlinePaymentError("Online payment isn't available for this invoice. Please use the banking details on the invoice.")
        if invoice.status not in PAYABLE or amount_due(invoice) <= 0:
            raise OnlinePaymentError("There is nothing left to pay on this invoice.", "ONLINE_PAYMENT_NOTHING_DUE")
        if not payer_email:
            raise OnlinePaymentError("Please enter your email address for the receipt.", "ONLINE_PAYMENT_EMAIL")
        company = await CompanySettingsRepository(self.db).get_current()
        attempt = OnlinePayment(
            invoice_id=invoice.id,
            provider=conn.provider,
            reference=f"YGT-{uuid.uuid4().hex[:24]}",
            amount=amount_due(invoice),
            currency=(company.default_currency or "ZAR").upper(),
            status="pending",
        )
        self.db.add(attempt)
        await self.db.flush()
        try:
            url = await providers.paystack_start(
                self.channels.secrets_of(conn),
                email=payer_email,
                amount_cents=_cents(attempt.amount),
                currency=attempt.currency,
                reference=attempt.reference,
                callback_url=return_url,
                # cancel_action: where Paystack's "Cancel payment" leads.
                metadata={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number, "source": "ygt-invoice", **({"cancel_action": cancel_url} if cancel_url else {})},
            )
        except ProviderError as exc:
            # Paystack never opened a checkout: nothing to check later.
            attempt.status, attempt.last_error = "not_started", str(exc)[:500]
            await self.db.flush()
            logger.warning("Paystack checkout failed for invoice %s: %s", invoice.id, exc)
            raise OnlinePaymentError("We couldn't open the payment page just now. Please try again in a few minutes.", "ONLINE_PAYMENT_PROVIDER") from exc
        return url

    async def settle(self, reference: str) -> OnlinePayment | None:
        """Asks Paystack how a payment went and, if it went through, records
        it against the invoice once. Safe to call any number of times."""
        attempt = await self.db.scalar(select(OnlinePayment).where(OnlinePayment.reference == reference).with_for_update())
        # Only these are final. "failed" isn't: on Paystack's checkout a
        # declined card can be retried with another, on the same reference.
        if attempt is None or attempt.status in ("paid", "needs_attention", "not_started"):
            return attempt
        conn = await self.channels.get("payments")
        if conn is None or conn.provider != attempt.provider:
            return attempt
        try:
            data = await providers.paystack_verify(self.channels.secrets_of(conn), reference)
        except ProviderError as exc:
            attempt.last_error = str(exc)[:500]
            await self.db.flush()
            return attempt
        outcome = data.get("status")
        if outcome != "success":
            if outcome == "failed":
                attempt.status = "failed"
            attempt.last_error = (data.get("gateway_response") or outcome or "")[:500] or None
            await self.db.flush()
            return attempt

        invoice = await self.db.scalar(
            select(Invoice).where(Invoice.id == attempt.invoice_id).with_for_update().execution_options(populate_existing=True)
        )
        attempt.channel = (data.get("channel") or "")[:30] or None
        attempt.paid_at = _paid_at(data.get("paid_at") or data.get("paidAt"))
        if data.get("amount") != _cents(attempt.amount) or (data.get("currency") or "").upper() != attempt.currency:
            # Never seen in practice; recorded for a person to look at, not guessed.
            return await self._needs_attention(attempt, invoice, "Paystack reported a different amount or currency from the one YGT asked for.")
        try:
            payment = await PaymentService(self.db).record_payment(
                attempt.invoice_id,
                PaymentCreate(
                    amount=Decimal(attempt.amount),
                    method=_METHODS.get(attempt.channel or "", PaymentMethod.OTHER),
                    reference=reference,
                    paid_at=attempt.paid_at,
                    notes=f"Paid online with Paystack{f' ({attempt.channel})' if attempt.channel else ''}",
                ),
                recorded_by_id=None,
            )
        except ConflictError:
            return await self._needs_attention(
                attempt, invoice, "The customer paid online, but the invoice no longer needed it (it was paid another way or cancelled)."
            )
        attempt.status, attempt.payment_id, attempt.last_error = "paid", payment.id, None
        await self.db.flush()
        balance = amount_due(invoice)
        await self._tell_team(
            invoice,
            key=f"online-paid:{reference}",
            title=f"{invoice.invoice_number} paid {_money(attempt.currency, attempt.amount)} online",
            body="Paid in full." if balance <= 0 else f"{_money(attempt.currency, balance)} is still owed.",
        )
        from app.api.email_dispatch import commit_and_enqueue
        from app.tasks.email_tasks import send_payment_receipt_task

        await commit_and_enqueue(self.db, send_payment_receipt_task, str(payment.id))
        return attempt

    async def _needs_attention(self, attempt: OnlinePayment, invoice: Invoice, reason: str) -> OnlinePayment:
        attempt.status, attempt.last_error = "needs_attention", reason[:500]
        await self.db.flush()
        await self._tell_team(
            invoice,
            key=f"online-attention:{attempt.reference}",
            title=f"Check an online payment for {invoice.invoice_number}",
            body=f"{reason} {_money(attempt.currency, attempt.amount)}, Paystack reference {attempt.reference}. "
            "Refund it in Paystack, or keep it and record it yourself.",
        )
        return attempt

    async def _tell_team(self, invoice: Invoice, *, key: str, title: str, body: str) -> None:
        """Whoever made the invoice, and the company's admins."""
        people = list(
            (await self.db.scalars(select(User).where(User.is_active.is_(True), (User.role == UserRole.ADMIN) | (User.id == invoice.created_by)))).all()
        )
        for person in people:
            await notify(self.db, person, kind="online_payment", title=title, body=body, link=f"/invoices/{invoice.id}", key=key)
        if not people:
            await self.db.commit()


async def check_pending(now: datetime | None = None) -> int:
    """Confirms checkouts nobody came back from (the customer closed the tab,
    or the webhook isn't set up). Each runs in its own company's session."""
    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system, set_tenant

    now = now or datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        set_system(db)
        rows = (
            await db.execute(
                select(OnlinePayment.reference, OnlinePayment.company_id, OnlinePayment.created_at).where(
                    OnlinePayment.status.in_(("pending", "failed")), OnlinePayment.created_at <= now - timedelta(minutes=2)
                )
            )
        ).all()
    settled = 0
    for reference, company_id, created_at in rows:
        async with AsyncSessionLocal() as db:
            set_tenant(db, company_id)
            try:
                attempt = await OnlinePaymentService(db).settle(reference)
                if attempt is not None and attempt.status in ("pending", "failed") and created_at <= now - GIVE_UP_AFTER:
                    attempt.status = "abandoned"
                settled += attempt is not None and attempt.status == "paid"
                await db.commit()
            except Exception:
                logger.exception("Could not check online payment %s", reference)
                await db.rollback()
    return settled
