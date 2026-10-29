"""Prospects and marketing consent (POPIA s69).

A prospect isn't a customer yet, so marketing may only go to them once
they've agreed to it. Agreement is recorded with when and how; a prospect
may be asked once, by a personal email whose reply link records the answer.
Saying no opts them out, exactly like unsubscribing."""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.customer import Customer
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.documents import resolve_template
from app.services.campaign_service import _paragraphs, public_url
from app.services.email_service import render_email, send_email
from app.services.email_settings import resolve_email_config
from app.services.notification_service import _money_formatter

# Added to every invite, whatever the message says: the promise that makes
# it a one-time request rather than the start of a mailing list.
INVITE_PROMISE = "We won't email you again unless you say yes."
SAID_YES = "Said yes to the email invite"


class ProspectError(AppError):
    def __init__(self, message: str, error_code: str):
        super().__init__(message, error_code, status.HTTP_409_CONFLICT)


class ProspectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_prospects(self, search: str | None = None) -> list[Customer]:
        query = select(Customer).where(Customer.is_prospect.is_(True), Customer.is_active.is_(True))
        if search:
            query = query.where(Customer.name.ilike(f"%{search}%"))
        return list((await self.db.scalars(query.order_by(Customer.created_at.desc()).limit(500))).all())

    async def get(self, prospect_id: uuid.UUID) -> Customer:
        prospect = await self.db.get(Customer, prospect_id)
        if prospect is None or not prospect.is_prospect:
            raise NotFoundError("Prospect not found", "PROSPECT_NOT_FOUND")
        return prospect

    async def set_consent(self, prospect_id: uuid.UUID, agreed: bool, source: str | None) -> Customer:
        """Records (or withdraws) a prospect's agreement to marketing. Agreeing
        again after an opt-out is their choice to make, so it lifts the opt-out."""
        prospect = await self.get(prospect_id)
        now = datetime.now(timezone.utc)
        if agreed:
            if not (source or "").strip():
                raise AppError("Say how they agreed, for example by phone or on a form", "CONSENT_SOURCE_REQUIRED")
            prospect.marketing_consent_at = now
            prospect.marketing_consent_source = source.strip()[:200]
            prospect.marketing_opt_out = False
            prospect.marketing_opt_out_at = None
        else:
            prospect.marketing_consent_at = None
            prospect.marketing_consent_source = None
        await self.db.flush()
        return prospect

    async def invite(self, prospect_id: uuid.UUID, subject: str, message: str) -> Customer:
        """The one approach s69 allows: a personal email asking whether they'd
        like to hear from the company, with a yes/no link. Sent once, ever."""
        prospect = await self.get(prospect_id)
        to = prospect.recipient_email
        if not to:
            raise ProspectError("This prospect has no email address", "PROSPECT_NO_EMAIL")
        if prospect.marketing_opt_out:
            raise ProspectError("They've said no to marketing", "PROSPECT_OPTED_OUT")
        if prospect.marketing_consent_at:
            raise ProspectError("They've already agreed to marketing", "PROSPECT_ALREADY_AGREED")
        if prospect.consent_invited_at:
            raise ProspectError("They've already been asked once", "PROSPECT_ALREADY_INVITED")
        company = await CompanySettingsRepository(self.db).get_current()
        token = secrets.token_urlsafe(32)
        reply = public_url(f"m/c/{token}")
        name = (prospect.name or "").split(" ")[0] or "there"
        email = render_email(
            "campaign",
            to=to,
            subject=subject.replace("{name}", name).strip() or f"{company.company_name} would like to keep in touch",
            preheader=None,
            paragraphs=_paragraphs(f"{message.strip()}\n\n{INVITE_PROMISE}", name),
            products=[],
            cta_text="Yes, keep me posted",
            cta_url=reply,
            unsubscribe_url=reply,
            pixel_url=None,
            company=company,
            accent=resolve_template(company).accent,
            money=_money_formatter(company.default_currency),
        )
        email.headers["List-Unsubscribe"] = f"<{public_url(f'm/c/{token}/no')}>"
        email.headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        await run_in_threadpool(send_email, resolve_email_config(company), email)
        prospect.consent_token = token
        prospect.consent_invited_at = datetime.now(timezone.utc)
        await self.db.flush()
        return prospect

    async def reply(self, token: str, agreed: bool) -> tuple[bool, str]:
        """Records the answer from an invite's link. Returns (found, company name)."""
        prospect = await self.db.scalar(select(Customer).where(Customer.consent_token == token))
        if prospect is None:
            return False, ""
        company = await CompanySettingsRepository(self.db).get_for(prospect.company_id)
        now = datetime.now(timezone.utc)
        if agreed:
            prospect.marketing_consent_at = prospect.marketing_consent_at or now
            prospect.marketing_consent_source = prospect.marketing_consent_source or SAID_YES
            prospect.marketing_opt_out = False
            prospect.marketing_opt_out_at = None
        else:
            prospect.marketing_consent_at = None
            prospect.marketing_consent_source = None
            prospect.marketing_opt_out = True
            prospect.marketing_opt_out_at = prospect.marketing_opt_out_at or now
        await self.db.flush()
        return True, company.company_name
