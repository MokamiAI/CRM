"""Paystack API client for YGT's own subscription billing.

Uses the platform's secret key (PAYSTACK_SECRET_KEY), never a company's.
Amounts are in the currency's subunit (cents for ZAR)."""
import hashlib
import hmac

import httpx
from fastapi import status

from app.core.config import settings
from app.core.exceptions import AppError

_TIMEOUT = httpx.Timeout(20.0)


class PaystackError(AppError):
    def __init__(self, message: str, error_code: str = "BILLING_PROVIDER_ERROR", status_code: int = status.HTTP_502_BAD_GATEWAY):
        super().__init__(message, error_code, status_code)


def configured() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


async def _call(method: str, path: str, **kwargs) -> dict:
    if not configured():
        raise PaystackError("Online payments are not set up yet", "BILLING_NOT_CONFIGURED", status.HTTP_503_SERVICE_UNAVAILABLE)
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    try:
        async with httpx.AsyncClient(base_url=settings.PAYSTACK_API_BASE, timeout=_TIMEOUT) as client:
            response = await client.request(method, path, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise PaystackError(f"Could not reach Paystack: {exc.__class__.__name__}") from exc
    try:
        body = response.json()
    except ValueError:
        raise PaystackError(f"Paystack returned HTTP {response.status_code}")
    # Paystack: {"status": true|false, "message": "...", "data": ...}
    if response.status_code >= 400 or not body.get("status"):
        raise PaystackError(f"Paystack: {body.get('message') or response.status_code}")
    return body.get("data")


async def create_plan(name: str, amount_cents: int, interval: str) -> str:
    data = await _call("POST", "/plan", json={"name": name, "amount": amount_cents, "interval": interval, "currency": "ZAR"})
    return data["plan_code"]


async def initialize(email: str, amount_cents: int, plan_code: str, reference: str, callback_url: str, metadata: dict) -> str:
    """Starts checkout; returns the Paystack page to send the person to.
    With a plan, Paystack charges the plan's amount and then subscribes the
    card to it, renewing automatically."""
    data = await _call(
        "POST",
        "/transaction/initialize",
        json={
            "email": email,
            "amount": amount_cents,
            "currency": "ZAR",
            "plan": plan_code,
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        },
    )
    return data["authorization_url"]


async def verify(reference: str) -> dict:
    return await _call("GET", f"/transaction/verify/{reference}")


async def subscriptions_for(customer_id: int | str) -> list[dict]:
    return await _call("GET", "/subscription", params={"customer": customer_id}) or []


async def disable(subscription_code: str, email_token: str) -> None:
    await _call("POST", "/subscription/disable", json={"code": subscription_code, "token": email_token})


async def manage_link(subscription_code: str) -> str:
    """A Paystack page where the customer can change the card on file."""
    data = await _call("GET", f"/subscription/{subscription_code}/manage/link")
    return data["link"]


def signature_ok(raw_body: bytes, signature: str | None) -> bool:
    """Paystack signs each webhook with HMAC-SHA512 of the body, keyed by
    the secret key, in the x-paystack-signature header."""
    if not configured() or not signature:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


async def refund(reference: str, amount_cents: int | None = None) -> dict:
    """Refunds a charge, in full or in part. Paystack returns the refund
    (status pending, then processed once the money goes back to the card)."""
    body = {"transaction": reference}
    if amount_cents:
        body["amount"] = amount_cents
    return await _call("POST", "/refund", json=body)
