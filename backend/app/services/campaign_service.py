import secrets
import uuid
from datetime import date, datetime, timezone

from fastapi import status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.documents import resolve_template
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.models.customer import Customer
from app.models.marketing import Campaign, CampaignRecipient
from app.models.product import Product
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.marketing import CampaignIn, CampaignStats
from app.services.email_service import OutgoingEmail, render_email
from app.services.notification_service import _money_formatter
from app.services.segment_service import SegmentService

EDITABLE = ("draft", "scheduled")


class CampaignStateError(AppError):
    def __init__(self, message: str, error_code: str = "CAMPAIGN_NOT_EDITABLE"):
        super().__init__(message, error_code, status.HTTP_409_CONFLICT)


def public_url(path: str) -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/{path}"


def _paragraphs(body: str, name: str) -> list[list[str]]:
    """Blank-line separated paragraphs, each a list of lines. "{name}" is
    replaced with the recipient's name for a personal greeting."""
    text = body.replace("{name}", name).replace("\r\n", "\n").strip()
    return [block.split("\n") for block in text.split("\n\n") if block.strip()]


def _featured(product: Product, today: date) -> dict:
    on_special = product.special_price is not None and (
        product.special_until is None or product.special_until >= today
    )
    return {
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "price": product.unit_price,
        "special_price": product.special_price,
        "special_until": product.special_until,
        "on_special": on_special,
    }


class CampaignService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- CRUD ----------

    async def list_campaigns(self) -> list[Campaign]:
        query = select(Campaign).order_by(Campaign.created_at.desc())
        return list((await self.db.scalars(query)).all())

    async def get_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = await self.db.get(Campaign, campaign_id)
        if campaign is None:
            raise NotFoundError("Campaign not found", "CAMPAIGN_NOT_FOUND")
        return campaign

    @staticmethod
    def _apply(campaign: Campaign, data: CampaignIn) -> None:
        values = data.model_dump()
        values["cta_url"] = str(data.cta_url) if data.cta_url else None
        for name, value in values.items():
            setattr(campaign, name, value)

    async def create_campaign(self, data: CampaignIn, created_by: uuid.UUID) -> Campaign:
        if data.segment_id:
            await SegmentService(self.db).get_segment(data.segment_id)
        campaign = Campaign(created_by=created_by, status="draft")
        self._apply(campaign, data)
        self.db.add(campaign)
        await self.db.flush()
        return campaign

    async def update_campaign(self, campaign_id: uuid.UUID, data: CampaignIn) -> Campaign:
        campaign = await self.get_campaign(campaign_id)
        if campaign.status not in EDITABLE:
            raise CampaignStateError("A campaign can't be changed once it has been sent")
        if data.segment_id:
            await SegmentService(self.db).get_segment(data.segment_id)
        self._apply(campaign, data)
        await self.db.flush()
        return campaign

    async def delete_campaign(self, campaign_id: uuid.UUID) -> None:
        campaign = await self.get_campaign(campaign_id)
        if campaign.status not in EDITABLE:
            raise CampaignStateError("A sent campaign is kept as a record and can't be deleted")
        await self.db.delete(campaign)
        await self.db.flush()

    async def duplicate(self, campaign_id: uuid.UUID, created_by: uuid.UUID) -> Campaign:
        source = await self.get_campaign(campaign_id)
        copy = Campaign(
            name=f"{source.name} (copy)"[:150],
            subject=source.subject,
            preheader=source.preheader,
            body=source.body,
            product_ids=list(source.product_ids),
            cta_text=source.cta_text,
            cta_url=source.cta_url,
            segment_id=source.segment_id,
            status="draft",
            created_by=created_by,
        )
        self.db.add(copy)
        await self.db.flush()
        return copy

    # ---------- Stats ----------

    async def stats_for(self, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, CampaignStats]:
        if not campaign_ids:
            return {}
        r = CampaignRecipient
        rows = await self.db.execute(
            select(
                r.campaign_id,
                func.count(),
                func.count(case((r.status == "sent", 1))),
                func.count(case((r.status == "failed", 1))),
                func.count(r.opened_at),
                func.count(r.unsubscribed_at),
            )
            .where(r.campaign_id.in_(campaign_ids))
            .group_by(r.campaign_id)
        )
        return {
            row[0]: CampaignStats(recipients=row[1], sent=row[2], failed=row[3], opened=row[4], unsubscribed=row[5])
            for row in rows
        }

    async def recipients(self, campaign_id: uuid.UUID) -> list[tuple[CampaignRecipient, str | None]]:
        rows = await self.db.execute(
            select(CampaignRecipient, Customer.name)
            .outerjoin(Customer, Customer.id == CampaignRecipient.customer_id)
            .where(CampaignRecipient.campaign_id == campaign_id)
            .order_by(Customer.name)
        )
        return list(rows.tuples())

    # ---------- Composing ----------

    async def _products(self, ids: list[uuid.UUID]) -> list[Product]:
        if not ids:
            return []
        found = {p.id: p for p in (await self.db.scalars(select(Product).where(Product.id.in_(ids)))).all()}
        return [found[i] for i in ids if i in found]  # keep the chosen order

    async def compose(self, campaign: Campaign, to: str, name: str, token: str | None) -> OutgoingEmail:
        """Renders the campaign for one recipient. token=None is a preview or
        test send: links work but nothing is tracked against a customer."""
        company = await CompanySettingsRepository(self.db).get_for(campaign.company_id)
        today = date.today()
        unsubscribe = public_url(f"m/u/{token}") if token else public_url("m/u/preview")
        email = render_email(
            "campaign",
            to=to,
            subject=campaign.subject or campaign.name,
            preheader=campaign.preheader,
            paragraphs=_paragraphs(campaign.body, name),
            products=[_featured(p, today) for p in await self._products(campaign.product_ids)],
            cta_text=campaign.cta_text,
            cta_url=campaign.cta_url,
            unsubscribe_url=unsubscribe,
            pixel_url=public_url(f"m/o/{token}.gif") if token else None,
            company=company,
            accent=resolve_template(company).accent,  # the company's colour
            money=_money_formatter(company.default_currency),
        )
        email.headers["List-Unsubscribe"] = f"<{unsubscribe}>"
        email.headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        return email

    # ---------- Sending ----------

    async def schedule(self, campaign_id: uuid.UUID, when: datetime | None) -> Campaign:
        """when=None queues it now (returns status "sending"; the caller
        enqueues the worker task). A future time parks it as "scheduled"
        for the beat task to pick up."""
        campaign = await self.get_campaign(campaign_id)
        if campaign.status not in EDITABLE:
            raise CampaignStateError("This campaign has already been sent")
        if not campaign.subject.strip() or not campaign.body.strip():
            raise CampaignStateError("Add a subject and a message before sending", "CAMPAIGN_INCOMPLETE")
        if when is not None and when > datetime.now(timezone.utc):
            campaign.status = "scheduled"
            campaign.scheduled_at = when
            await self.db.flush()
            return campaign
        await self.start_sending(campaign)
        return campaign

    async def unschedule(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = await self.get_campaign(campaign_id)
        if campaign.status != "scheduled":
            raise CampaignStateError("Only a scheduled campaign can be moved back to draft")
        campaign.status = "draft"
        campaign.scheduled_at = None
        await self.db.flush()
        return campaign

    async def start_sending(self, campaign: Campaign) -> int:
        """Freezes the audience into recipient rows and marks the campaign
        as sending. The audience is resolved now, not when the draft was
        written, so opt-outs since then are respected."""
        segments = SegmentService(self.db)
        customers = await segments.audience(await segments.rules_for(campaign.segment_id))
        seen: set[str] = set()
        for customer in customers:
            address = customer.recipient_email.strip().lower()
            if address in seen:
                continue
            seen.add(address)
            self.db.add(
                CampaignRecipient(
                    campaign_id=campaign.id,
                    customer_id=customer.id,
                    email=customer.recipient_email.strip(),
                    token=secrets.token_urlsafe(24),
                    status="queued",
                )
            )
        campaign.status = "sending" if seen else "sent"
        campaign.sent_at = datetime.now(timezone.utc)
        campaign.scheduled_at = None
        await self.db.flush()
        return len(seen)

    async def due_campaigns(self) -> list[Campaign]:
        query = select(Campaign).where(
            Campaign.status == "scheduled", Campaign.scheduled_at <= datetime.now(timezone.utc)
        )
        return list((await self.db.scalars(query)).all())

    # ---------- Public tracking ----------

    async def _recipient(self, token: str) -> CampaignRecipient | None:
        return await self.db.scalar(select(CampaignRecipient).where(CampaignRecipient.token == token))

    async def record_open(self, token: str) -> None:
        recipient = await self._recipient(token)
        if recipient is None:
            return
        recipient.open_count += 1
        if recipient.opened_at is None:
            recipient.opened_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def unsubscribe(self, token: str) -> tuple[bool, str]:
        """Opts the recipient's customer out of all marketing. Returns
        (found, company name) for the confirmation page."""
        recipient = await self._recipient(token)
        if recipient is None:
            return False, ""
        company = await CompanySettingsRepository(self.db).get_for(recipient.company_id)
        now = datetime.now(timezone.utc)
        recipient.unsubscribed_at = recipient.unsubscribed_at or now
        if recipient.customer_id:
            customer = await self.db.get(Customer, recipient.customer_id)
            if customer and not customer.marketing_opt_out:
                customer.marketing_opt_out = True
                customer.marketing_opt_out_at = now
        await self.db.flush()
        return True, company.company_name
