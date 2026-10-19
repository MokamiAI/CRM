"""Purpose-limited signed customer acceptance links; GET never changes a quote."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.core.tenancy import set_tenant
from app.models.crm import Contact, Deal
from app.models.quote import Quote
import jwt


async def quote_recipient(db, quote, customer):
    if quote.deal_id:
        deal = await db.get(Deal, quote.deal_id)
        if deal and deal.contact_id:
            contact = await db.get(Contact, deal.contact_id)
            if contact and contact.customer_id == quote.customer_id and contact.email:
                return contact.email
    # The customer model exposes the shared contact-first recipient.
    return customer.recipient_email


def acceptance_url(quote):
    token = jwt.encode({
        "type": "quote-acceptance", "sub": str(quote.id),
        "company": str(quote.company_id), "version": quote.updated_at.isoformat(),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/quotes/accept/{token}"


async def linked_quote(db, token):
    try:
        payload = decode_token(token)
        if payload.get("type") != "quote-acceptance":
            raise ValueError()
        company_id, quote_id = uuid.UUID(payload["company"]), uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise UnauthorizedError("This quote acceptance link is invalid or has expired")
    set_tenant(db, company_id)
    quote = await db.scalar(select(Quote).where(Quote.id == quote_id).with_for_update())
    if quote is None:
        raise UnauthorizedError("This quote acceptance link is invalid")
    # Revisions invalidate earlier links. Completed acceptance stays repeatable.
    if quote.status.value not in ("accepted", "converted") and quote.updated_at.isoformat() != payload.get("version"):
        raise UnauthorizedError("This quote has changed. Please use the latest email")
    return quote
