"""YGT's help desk: companies log tickets from their Support tab and see
the replies; YGT's team works them in the admin site. Whoever is waiting
gets an email when it's their turn."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.plans import PRIORITY_SUPPORT
from app.core.tenancy import ALL_TENANTS
from app.models.company_settings import CompanySettings
from app.models.platform import SupportTicket, TicketMessage
from app.models.user import User
from app.services import platform_email
from app.services.billing_service import BillingService

CATEGORY_LABELS = {"question": "Question", "problem": "Something isn't working", "billing": "Billing", "feature": "Feature idea", "account": "Account"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# How help desk emails are signed: the name people see, not an inbox.
SUPPORT_SENDER = "YGT Support"

class HelpdeskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- a company's own tickets ----------

    async def list_mine(self) -> list[SupportTicket]:
        return list(await self.db.scalars(select(SupportTicket).order_by(SupportTicket.last_message_at.desc())))

    async def get_mine(self, ticket_id: uuid.UUID) -> SupportTicket:
        ticket = await self.db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id))
        if ticket is None:
            raise NotFoundError("Ticket not found", "TICKET_NOT_FOUND")
        return ticket

    async def messages(self, ticket: SupportTicket, *, include_internal: bool) -> list[TicketMessage]:
        query = select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at)
        if not include_internal:
            query = query.where(TicketMessage.internal.is_(False))
        return list(await self.db.scalars(query.execution_options(**{ALL_TENANTS: include_internal})))

    async def open_ticket(self, user: User, subject: str, category: str, urgency: str, body: str) -> SupportTicket:
        current = await BillingService(self.db).current()
        ticket = SupportTicket(
            company_id=user.company_id,
            subject=subject.strip(),
            category=category,
            urgency=urgency,
            created_by=user.id,
            priority_plan=PRIORITY_SUPPORT in current.plan.features,
            last_message_at=_now(),
        )
        self.db.add(ticket)
        await self.db.flush()
        self.db.add(TicketMessage(company_id=user.company_id, ticket_id=ticket.id, author_name=user.full_name, author_user_id=user.id, body=body.strip()))
        await self.db.flush()
        await self.db.refresh(ticket)
        company = await self.db.get(CompanySettings, user.company_id)
        await self._acknowledge(ticket, user)
        await self._tell_team(ticket, company, user, body, new=True)
        return ticket

    async def reply_as_company(self, ticket: SupportTicket, user: User, body: str) -> TicketMessage:
        if ticket.status == "closed":
            raise AppError("This ticket is closed. Open a new one if you still need help.", "TICKET_CLOSED")
        message = TicketMessage(company_id=ticket.company_id, ticket_id=ticket.id, author_name=user.full_name, author_user_id=user.id, body=body.strip())
        self.db.add(message)
        ticket.last_message_at = _now()
        ticket.last_from_platform = False
        if ticket.status in ("waiting", "resolved"):
            ticket.status = "open"  # their reply puts it back in YGT's queue
            ticket.closed_at = None
        await self.db.flush()
        company = await self.db.get(CompanySettings, ticket.company_id)
        await self._tell_team(ticket, company, user, body, new=False)
        return message

    async def close_as_company(self, ticket: SupportTicket) -> SupportTicket:
        ticket.status = "closed"
        ticket.closed_at = _now()
        await self.db.flush()
        return ticket

    # ---------- YGT's team (admin site, SYSTEM session) ----------

    async def admin_get(self, ticket_id: uuid.UUID) -> SupportTicket:
        ticket = await self.db.get(SupportTicket, ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found", "TICKET_NOT_FOUND")
        return ticket

    async def reply_as_team(self, ticket: SupportTicket, admin: User, body: str, internal: bool) -> TicketMessage:
        message = TicketMessage(
            company_id=ticket.company_id, ticket_id=ticket.id, author_name="YGT support" if not internal else admin.full_name,
            author_user_id=admin.id, from_platform=True, internal=internal, body=body.strip(),
        )
        self.db.add(message)
        if not internal:
            ticket.last_message_at = _now()
            ticket.last_from_platform = True
            if ticket.status in ("open", "in_progress"):
                ticket.status = "waiting"  # their turn
        await self.db.flush()
        if not internal:
            await self._tell_company(ticket, body)
        return message

    async def update(self, ticket: SupportTicket, status: str | None, urgency: str | None, assigned_to: str | None) -> SupportTicket:
        if status:
            ticket.status = status
            ticket.closed_at = _now() if status in ("resolved", "closed") else None
        if urgency:
            ticket.urgency = urgency
        if assigned_to is not None:
            ticket.assigned_to = assigned_to or None
        await self.db.flush()
        if status == "resolved":
            await self._tell_company(ticket, None, resolved=True)
        return ticket

    # ---------- emails ----------

    async def _tell_team(self, ticket: SupportTicket, company, user: User, body: str, new: bool) -> None:
        if not settings.SUPPORT_EMAIL:
            return
        flag = " [PRIORITY]" if ticket.priority_plan else ""
        email = platform_email.compose(
            to=settings.SUPPORT_EMAIL,
            subject=f"{'New ticket' if new else 'Reply on'} #{ticket.number}{flag}: {ticket.subject}",
            title=f"{'New ticket' if new else 'New reply on ticket'} #{ticket.number}",
            paragraphs=[f"{user.full_name} at {company.company_name if company else 'a company'} wrote:"],
            details=[
                ("Subject", ticket.subject),
                ("Category", CATEGORY_LABELS.get(ticket.category, ticket.category)),
                ("Urgency", ticket.urgency.title()),
                ("Priority support", "Yes (Scale plan)" if ticket.priority_plan else "No"),
            ],
            quote=body,
            button=("Open in the admin site", platform_email.app_link(f"/admin/tickets/{ticket.id}")),
            reply_to=user.email,
        )
        await platform_email.queue(self.db, email)

    async def _acknowledge(self, ticket: SupportTicket, user: User) -> None:
        """The automatic reply: their ticket is logged and what happens next.
        Sent as "YGT Support" from YGT's sending address, never the team's
        private inbox."""
        email = platform_email.compose(
            to=user.email,
            subject=f"We've received your ticket #{ticket.number}: {ticket.subject}",
            title=f"We've received your ticket #{ticket.number}",
            paragraphs=[
                f"Hi {user.full_name.split(' ')[0]},",
                "Thanks for getting in touch. Your ticket is logged and our support team will get back to you, usually within one working day."
                + (" Your Scale plan includes priority support, so you're at the front of the queue." if ticket.priority_plan else ""),
                "We'll email you when we reply. You can add more details or follow the ticket in YGT at any time.",
            ],
            details=[("Ticket", f"#{ticket.number}"), ("Subject", ticket.subject), ("Urgency", ticket.urgency.title())],
            button=("View the ticket", platform_email.app_link(f"/support/tickets/{ticket.id}")),
            from_name=SUPPORT_SENDER,
        )
        await platform_email.queue(self.db, email)

    async def _tell_company(self, ticket: SupportTicket, body: str | None, resolved: bool = False) -> None:
        author = await self.db.get(User, ticket.created_by) if ticket.created_by else None
        if author is None:
            return
        email = platform_email.compose(
            to=author.email,
            subject=f"{'Resolved' if resolved else 'Reply'}: #{ticket.number} {ticket.subject}",
            title=f"Ticket #{ticket.number} has been resolved" if resolved else f"YGT support replied to ticket #{ticket.number}",
            paragraphs=[f"Hi {author.full_name.split(' ')[0]},"]
            + (["We've marked your ticket as resolved. If something still isn't right, just reply in the app and it will reopen."] if resolved else []),
            quote=body,
            button=("View the ticket", platform_email.app_link(f"/support/tickets/{ticket.id}")),
            from_name=SUPPORT_SENDER,
        )
        await platform_email.queue(self.db, email)
