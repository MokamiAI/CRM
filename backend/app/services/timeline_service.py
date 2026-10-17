import uuid
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.crm import Activity, Contact, Deal, Note
from app.models.customer import Customer
from app.models.enums import DealStage
from app.models.invoice import Invoice
from app.models.messaging import Conversation, Message
from app.models.payment import Payment
from app.models.quote import Quote
from app.models.reminder import ReminderLog
from app.schemas.crm import SearchHit, TimelineItem

_LIMIT = 150


def _money(amount) -> str:
    return f"{Decimal(amount):,.2f}"


def _activity_item(activity: Activity) -> TimelineItem:
    return TimelineItem(
        kind="activity",
        at=activity.done_at or activity.updated_at,
        title=f"{activity.type.value.capitalize()} completed: {activity.subject}",
        detail=activity.note,
        params={"type": activity.type.value, "subject": activity.subject},
        ref_id=activity.id,
        actor_id=activity.owner_id,
    )


def _note_item(note: Note) -> TimelineItem:
    return TimelineItem(kind="note", at=note.created_at, title="Note", detail=note.body, ref_id=note.id, actor_id=note.author_id)


def _deal_items(deal: Deal) -> list[TimelineItem]:
    items = [
        TimelineItem(
            kind="deal_created",
            at=deal.created_at,
            title=f"Deal created: {deal.title}",
            detail=f"Value {_money(deal.value)}",
            params={"title": deal.title, "value": str(deal.value)},
            ref_id=deal.id,
            actor_id=deal.created_by,
        )
    ]
    if deal.closed_at is not None and deal.stage in (DealStage.WON, DealStage.LOST):
        outcome = "won" if deal.stage == DealStage.WON else "lost"
        items.append(
            TimelineItem(
                kind="deal_closed",
                at=deal.closed_at,
                title=f"Deal {outcome}: {deal.title}",
                detail=deal.lost_reason if outcome == "lost" else f"Value {_money(deal.value)}",
                params={"title": deal.title, "outcome": outcome, "value": str(deal.value), "reason": deal.lost_reason or ""},
                ref_id=deal.id,
                actor_id=deal.owner_id,
            )
        )
    return items


def _quote_item(quote: Quote) -> TimelineItem:
    return TimelineItem(
        kind="quote",
        at=quote.created_at,
        title=f"Quote {quote.quote_number} · {quote.status.value}",
        detail=f"Total {_money(quote.total)}",
        params={"number": quote.quote_number, "status": quote.status.value, "total": str(quote.total)},
        ref_id=quote.id,
        actor_id=quote.created_by,
    )


class TimelineService:
    """A record's history in one chronological list, newest first: what was
    said (notes), done (completed activities), sold (deals, quotes) and
    billed (invoices, payments, reminders). Upcoming activities are not
    history; the client lists them separately above the timeline."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _all(self, stmt):
        return list((await self.db.execute(stmt)).scalars().all())

    async def _mcem(self, deal_ids):
        from app.models.mcem import McemEvent
        events = await self._all(select(McemEvent).where(McemEvent.deal_id.in_(deal_ids)).order_by(McemEvent.created_at.desc()).limit(_LIMIT))
        return [TimelineItem(kind="mcem", at=e.created_at, title="Customer progress: " + e.kind.replace("_", " "), detail=(f"{e.detail.get('from')} to {e.detail.get('to')}" if e.kind == "stage_changed" else e.detail.get("message") or e.detail.get("reason") or e.detail.get("key")), ref_id=e.deal_id, event_id=e.id, actor_id=e.actor_id) for e in events]

    async def customer_timeline(self, customer_id: uuid.UUID) -> list[TimelineItem]:
        if await self.db.get(Customer, customer_id) is None:
            raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")

        items: list[TimelineItem] = []
        items += [_note_item(n) for n in await self._all(select(Note).where(Note.customer_id == customer_id))]
        items += [
            _activity_item(a)
            for a in await self._all(select(Activity).where(Activity.customer_id == customer_id, Activity.done.is_(True)))
        ]
        for deal in await self._all(select(Deal).where(Deal.customer_id == customer_id)):
            items += _deal_items(deal)
        deal_ids = select(Deal.id).where(Deal.customer_id == customer_id)
        items += await self._mcem(deal_ids)
        items += [_quote_item(q) for q in await self._all(select(Quote).where(Quote.customer_id == customer_id))]

        invoices = await self._all(select(Invoice).where(Invoice.customer_id == customer_id))
        numbers = {i.id: i.invoice_number for i in invoices}
        items += [
            TimelineItem(
                kind="invoice",
                at=i.created_at,
                title=f"Invoice {i.invoice_number} · {i.status.value.replace('_', ' ')}",
                detail=f"Total {_money(i.total)}",
                params={"number": i.invoice_number, "status": i.status.value, "total": str(i.total)},
                ref_id=i.id,
                actor_id=i.created_by,
            )
            for i in invoices
        ]
        if numbers:
            ids = list(numbers)
            items += [
                TimelineItem(
                    kind="payment",
                    at=p.paid_at,
                    title=f"Payment received · {numbers[p.invoice_id]}",
                    params={"number": numbers[p.invoice_id], "amount": str(p.amount), "method": p.method.value, "reference": p.reference or ""},
                    detail=f"{_money(p.amount)} by {p.method.value.replace('_', ' ')}"
                    + (f" · ref {p.reference}" if p.reference else ""),
                    ref_id=p.invoice_id,
                    actor_id=p.recorded_by,
                )
                for p in await self._all(select(Payment).where(Payment.invoice_id.in_(ids)))
            ]
            items += [
                TimelineItem(
                    kind="reminder",
                    at=r.sent_at,
                    title=f"Payment reminder emailed · {numbers[r.invoice_id]}",
                    params={"number": numbers[r.invoice_id], "manual": "1" if r.reminder_type.startswith("manual") else "0"},
                    detail="Sent manually" if r.reminder_type.startswith("manual") else "Automatic reminder",
                    ref_id=r.invoice_id,
                )
                for r in await self._all(select(ReminderLog).where(ReminderLog.invoice_id.in_(ids)))
            ]

        # Emails with the customer from the inbox (internal notes stay there).
        rows = await self.db.execute(
            select(Message, Conversation.subject)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.customer_id == customer_id, Message.direction.in_(("in", "out")))
        )
        items += [
            TimelineItem(
                kind="message",
                at=m.created_at,
                title=f"{'Email from customer' if m.direction == 'in' else 'Email sent'}: {subject}",
                detail=m.body[:280],
                params={"direction": m.direction, "subject": subject},
                ref_id=m.conversation_id,
                actor_id=m.author_id,
            )
            for m, subject in rows.tuples()
        ]

        items.sort(key=lambda item: item.at, reverse=True)
        return items[:_LIMIT]

    async def deal_timeline(self, deal_id: uuid.UUID) -> list[TimelineItem]:
        deal = await self.db.get(Deal, deal_id)
        if deal is None:
            raise NotFoundError("Deal not found", "DEAL_NOT_FOUND")
        items = _deal_items(deal)
        items += await self._mcem([deal.id])
        items += [_note_item(n) for n in await self._all(select(Note).where(Note.deal_id == deal_id))]
        items += [
            _activity_item(a)
            for a in await self._all(select(Activity).where(Activity.deal_id == deal_id, Activity.done.is_(True)))
        ]
        items += [_quote_item(q) for q in await self._all(select(Quote).where(Quote.deal_id == deal_id))]
        items.sort(key=lambda item: item.at, reverse=True)
        return items[:_LIMIT]


class SearchService:
    """Global search for the command palette: a few best hits per kind."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, per_kind: int = 5) -> list[SearchHit]:
        q = query.strip()
        if len(q) < 2:
            return []
        like = f"%{q}%"
        run = lambda stmt: self.db.execute(stmt.limit(per_kind))  # noqa: E731
        hits: list[SearchHit] = []

        for c in (await run(select(Customer).where(or_(Customer.name.ilike(like), Customer.email.ilike(like))).order_by(Customer.name))).scalars():
            hits.append(SearchHit(kind="customer", id=c.id, title=c.name, subtitle=c.email, target_id=c.id))

        contacts = await run(
            select(Contact, Customer.name)
            .join(Customer, Customer.id == Contact.customer_id)
            .where(or_(Contact.first_name.ilike(like), Contact.last_name.ilike(like), Contact.email.ilike(like)))
        )
        for contact, company in contacts.all():
            name = " ".join(filter(None, [contact.first_name, contact.last_name]))
            hits.append(SearchHit(kind="contact", id=contact.id, title=name, subtitle=company, target_id=contact.customer_id))

        deals = await run(
            select(Deal, Customer.name).join(Customer, Customer.id == Deal.customer_id).where(Deal.title.ilike(like)).order_by(Deal.updated_at.desc())
        )
        for deal, company in deals.all():
            hits.append(SearchHit(kind="deal", id=deal.id, title=deal.title, subtitle=company, target_id=deal.id))

        invoices = await run(
            select(Invoice, Customer.name).join(Customer, Customer.id == Invoice.customer_id).where(Invoice.invoice_number.ilike(like))
        )
        for invoice, company in invoices.all():
            hits.append(SearchHit(kind="invoice", id=invoice.id, title=invoice.invoice_number, subtitle=company, target_id=invoice.id))

        quotes = await run(
            select(Quote, Customer.name).join(Customer, Customer.id == Quote.customer_id).where(Quote.quote_number.ilike(like))
        )
        for quote, company in quotes.all():
            hits.append(SearchHit(kind="quote", id=quote.id, title=quote.quote_number, subtitle=company, target_id=quote.id))

        return hits
