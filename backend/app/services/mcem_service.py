"""Evidence-backed sales gates and the linked post-sale customer journey."""
import uuid
from datetime import date

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect, select

from app.core.exceptions import ConflictError, NotFoundError
from app.models.crm import Activity, ActivityAttachment, Contact, Deal, Note
from app.models.enums import DealStage, UserRole
from app.models.mcem import McemJourney, McemMilestone, McemEvidence, McemEvent
from app.models.messaging import Conversation, Message
from app.models.quote import Quote
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.services.reminder_service import company_today

CATALOG = [
    ("fit", "Solution fit established", "Listen and Consult"),
    ("problem", "Problem understood", "Listen and Consult"),
    ("outcome", "Outcome agreed", "Listen and Consult"),
    ("solution", "Solution direction accepted", "Inspire and Design"),
    ("validation", "Solution validated", "Empower and Achieve"),
    ("proposal_review", "Proposal reviewed by customer", "Empower and Achieve"),
    ("agreement", "Commercial agreement confirmed", "Empower and Achieve"),
    ("delivery", "Delivery accepted", "Realize Value"),
    ("adoption", "Adoption reviewed", "Realize Value"),
    ("value", "Value reviewed", "Realize Value"),
    ("health", "Health and value review completed", "Manage and Optimize"),
    ("renewal", "Renewal decision recorded", "Manage and Optimize"),
    ("expansion", "New customer needs assessed", "Manage and Optimize"),
]
LABELS = {key: label for key, label, phase in CATALOG}
ORDER = ["lead", "qualified", "proposal", "negotiation", "won"]
GATES = {"qualified": ["fit"], "proposal": ["fit", "problem", "outcome", "solution"],
         "negotiation": ["fit", "problem", "outcome", "solution", "validation", "proposal_review"],
         "won": ["fit", "problem", "outcome", "solution", "validation", "proposal_review", "agreement"]}
POST_SALE = {"delivery", "adoption", "value", "health", "renewal", "expansion"}


def pipeline_phase(stage, milestones):
    """One phase calculation for opportunity details and the customer pipeline."""
    confirmed = {m.key for m in milestones if m.status == "confirmed" and not m.needs_review}
    if stage == DealStage.WON:
        return "Manage and Optimize" if {"delivery", "adoption", "value"}.issubset(confirmed) else "Realize Value"
    if stage in (DealStage.PROPOSAL, DealStage.NEGOTIATION):
        return "Empower and Achieve"
    return "Inspire and Design" if {"problem", "outcome"}.issubset(confirmed) else "Listen and Consult"


def record(row):
    return {c.key: getattr(row, c.key) for c in inspect(type(row)).columns}


class McemService:
    def __init__(self, db):
        self.db = db

    async def deal(self, deal_id, lock=False):
        query = select(Deal).where(Deal.id == deal_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        deal = await self.db.scalar(query)
        if deal is None:
            raise NotFoundError("Opportunity not found", "DEAL_NOT_FOUND")
        return deal

    async def today(self):
        company = await CompanySettingsRepository(self.db).get_current()
        return company_today(company.default_timezone)

    async def owner(self, user_id, strict=True):
        if user_id is not None:
            user = await self.db.get(User, user_id)
            if user is None or not user.is_active or user.role == UserRole.VIEWER:
                if strict:
                    raise ConflictError("Choose an active team member who can manage opportunities", "MCEM_OWNER_INVALID")
                return False
            return True
        return False

    def event(self, deal, actor_id, kind, detail):
        self.db.add(McemEvent(company_id=deal.company_id, deal_id=deal.id, actor_id=actor_id, kind=kind, detail=jsonable_encoder(detail)))

    async def journey(self, deal):
        row = await self.db.scalar(select(McemJourney).where(McemJourney.deal_id == deal.id))
        if row is None:
            raise ConflictError("Enable MCEM on this opportunity first", "MCEM_NOT_ENABLED")
        return row

    async def milestones(self, deal):
        return {m.key: m for m in await self.db.scalars(select(McemMilestone).where(McemMilestone.deal_id == deal.id))}

    async def enable(self, deal_id, actor):
        deal = await self.deal(deal_id, lock=True)
        if deal.mcem_enabled:
            return await self.detail(deal_id)
        owner_id = deal.owner_id or actor.id
        await self.owner(owner_id)
        deal.mcem_enabled = True
        deal.owner_id = owner_id
        self.db.add(McemJourney(company_id=deal.company_id, deal_id=deal.id, state="active" if deal.stage == DealStage.WON else "paused" if deal.stage == DealStage.LOST else "draft", delivery_owner_id=owner_id, account_owner_id=owner_id))
        for key, _, _ in CATALOG:
            self.db.add(McemMilestone(company_id=deal.company_id, deal_id=deal.id, key=key, owner_id=owner_id))
        self.event(deal, actor.id, "enabled", {"stage": deal.stage.value, "message": "Milestones start unconfirmed; no customer agreement has been inferred."})
        await self.db.flush()
        return await self.detail(deal_id)

    async def issues(self, deal, target, changes=None):
        if not deal.mcem_enabled:
            return []
        changes = changes or {}
        if target == "lost":
            return [] if (changes.get("lost_reason") or deal.lost_reason or "").strip() else ["Record the loss reason"]
        if target not in GATES:
            return []
        rows = await self.milestones(deal)
        journey = await self.journey(deal)
        errors = ["Confirm: " + LABELS[key] for key in GATES[target] if rows[key].status != "confirmed" or rows[key].needs_review]
        owner_id = changes.get("owner_id", deal.owner_id)
        if not owner_id:
            errors.append("Assign a sales owner")
        elif not await self.owner(owner_id, strict=False):
            errors.append("Assign an active sales owner")
        if target != "won":
            today = await self.today()
            planned = await self.db.scalar(select(Activity.id).where(Activity.deal_id == deal.id, Activity.done.is_(False), Activity.due_date >= today).limit(1))
            if planned is None:
                errors.append("Schedule a dated customer next action")
        if not journey.qualification_reason.strip():
            errors.append("Record why the opportunity qualifies")
        if target in ("proposal", "negotiation", "won"):
            if not journey.decision_process.strip():
                errors.append("Identify the customer decision process")
            if not journey.success_measure.strip():
                errors.append("Record the agreed success measure")
        if target == "won":
            if not journey.scope.strip() or not journey.commitments.strip():
                errors.append("Complete the handover scope and commitments")
            if not deal.contact_id:
                errors.append("Choose a customer contact for handover")
            if not journey.delivery_owner_id or not journey.account_owner_id:
                errors.append("Assign delivery and account owners")
            for owner in [journey.delivery_owner_id, journey.account_owner_id]:
                if owner and not await self.owner(owner, strict=False):
                    errors.append("Choose active delivery and account owners")
            if journey.next_review_date is None or journey.next_review_date < await self.today():
                errors.append("Schedule the first customer journey milestone or review")
        return errors

    async def transition(self, deal, target, changes, actor_id):
        if not deal.mcem_enabled or target == deal.stage.value:
            return
        # Moving backwards is allowed; the relevant later confirmations are
        # then explicitly returned for review. Moving forwards cannot skip gates.
        backward = deal.stage.value in ORDER and target in ORDER and ORDER.index(target) < ORDER.index(deal.stage.value)
        errors = [] if backward else await self.issues(deal, target, changes)
        if errors:
            raise ConflictError("Before moving to " + target.title() + ": " + "; ".join(errors), "MCEM_STAGE_NOT_READY")
        detail = await self.detail(deal.id)
        self.event(deal, actor_id, "stage_changed", {"from": deal.stage.value, "to": target, "phase": detail["phase"], "reason": changes.get("lost_reason")})
        journey = await self.journey(deal)
        journey.state = "active" if target == "won" else "paused" if deal.stage == DealStage.WON or target == "lost" else "draft"
        if backward:
            order = [key for key, _, _ in CATALOG]
            first = {"lead": "fit", "qualified": "problem", "proposal": "validation", "negotiation": "agreement"}[target]
            await self.invalidate(deal, set(order[order.index(first):]), actor_id, "Commercial stage revisited")

    async def invalidate(self, deal, keys, actor_id, reason):
        affected = []
        for key, row in (await self.milestones(deal)).items():
            if key in keys and row.status == "confirmed":
                affected.append({"key": key, "confirmed_on": row.confirmed_on, "confirmed_by": row.confirmed_by})
                row.status = "in_progress"
                row.needs_review = True
                row.confirmed_on = None
                row.confirmed_by = None
        if affected:
            self.event(deal, actor_id, "confirmation_review_required", {"reason": reason, "milestones": affected})

    async def update_journey(self, deal_id, data, actor):
        deal = await self.deal(deal_id, lock=True)
        if deal.stage == DealStage.LOST:
            raise ConflictError("Reopen the opportunity before changing its customer journey", "MCEM_LOST_READ_ONLY")
        journey = await self.journey(deal)
        changes = data.model_dump(exclude_unset=True)
        nullable = {"baseline", "target", "actual", "delivery_owner_id", "account_owner_id", "next_review_date", "renewal_date"}
        for key, value in list(changes.items()):
            if value is None and key not in nullable:
                raise ConflictError("Use an empty value to clear text fields", "MCEM_INVALID_VALUE")
            if key.endswith("owner_id"):
                await self.owner(value)
        differences = {key: {"from": getattr(journey, key), "to": value} for key, value in changes.items() if getattr(journey, key) != value}
        if any(key in differences and differences[key]["from"] not in (None, "") for key in ("scope", "success_measure", "baseline", "target", "unit")):
            await self.invalidate(deal, set(LABELS) - {"fit", "problem"}, actor.id, "Scope or agreed outcomes changed")
        for field, key in [("next_review_date", "health"), ("renewal_date", "renewal")]:
            if field in differences and differences[field]["to"] is not None:
                await self.invalidate(deal, {key}, actor.id, "A new customer review or renewal cycle was scheduled")
        for key, value in changes.items():
            setattr(journey, key, value.strip() if isinstance(value, str) else value)
        if differences:
            self.event(deal, actor.id, "journey_updated", differences)
        await self.db.flush()
        return await self.detail(deal_id)

    async def milestone(self, deal, key):
        row = (await self.milestones(deal)).get(key)
        if row is None:
            raise NotFoundError("Milestone not found", "MCEM_MILESTONE_NOT_FOUND")
        return row

    async def update_milestone(self, deal_id, key, data, actor):
        deal = await self.deal(deal_id, lock=True)
        row = await self.milestone(deal, key)
        if deal.stage == DealStage.LOST:
            raise ConflictError("Reopen this opportunity before changing its milestones", "MCEM_LOST_READ_ONLY")
        if key in POST_SALE and deal.stage != DealStage.WON:
            raise ConflictError("Post-sale milestones start after the opportunity is Won", "MCEM_NOT_WON")
        changes = data.model_dump(exclude_unset=True)
        if "owner_id" in changes:
            await self.owner(changes["owner_id"])
        if changes.get("status", row.status) is None or ("summary" in changes and changes["summary"] is None):
            raise ConflictError("Choose a milestone status and a valid summary", "MCEM_INVALID_VALUE")
        status = changes.get("status", row.status)
        if key == "renewal" and not (await self.journey(deal)).recurring:
            raise ConflictError("Renewal milestones apply only to recurring contracts", "MCEM_RENEWAL_NOT_APPLICABLE")
        if status == "confirmed":
            owner_id = changes.get("owner_id", row.owner_id)
            if owner_id is None:
                raise ConflictError("Assign a milestone owner before confirming it", "MCEM_OWNER_REQUIRED")
            await self.owner(owner_id)
            evidence = list(await self.db.scalars(select(McemEvidence).where(McemEvidence.milestone_id == row.id)))
            confirmation = changes.get("confirmed_on", row.confirmed_on)
            if not evidence or confirmation is None:
                raise ConflictError("Link dated customer evidence and choose the confirmation date first", "MCEM_EVIDENCE_REQUIRED")
            if confirmation > await self.today() or any(e.occurred_on > confirmation for e in evidence):
                raise ConflictError("Confirmation must be on or after the evidence date, and not in the future", "MCEM_CONFIRMATION_DATE")
            if key == "value":
                journey = await self.journey(deal)
                if not journey.success_measure.strip() or not (changes.get("summary", row.summary) or "").strip() or (journey.target is not None and journey.actual is None):
                    raise ConflictError("Record the measured results and explain any gaps before confirming value", "MCEM_VALUE_REVIEW_REQUIRED")
            changes.update(confirmed_on=confirmation, confirmed_by=actor.id, needs_review=False)
        else:
            changes.update(confirmed_on=None, confirmed_by=None)
        before = record(row)
        for name, value in changes.items():
            setattr(row, name, value.strip() if isinstance(value, str) else value)
        self.event(deal, actor.id, "milestone_updated", {"key": key, "before": before, "after": record(row)})
        if status == "confirmed" and key == "health":
            (await self.journey(deal)).next_review_date = None
        await self.db.flush()
        return await self.detail(deal_id)

    async def sources(self, deal_id):
        deal = await self.deal(deal_id)
        result = []
        notes = await self.db.scalars(select(Note).where((Note.deal_id == deal.id) | ((Note.deal_id.is_(None)) & (Note.customer_id == deal.customer_id))).order_by(Note.created_at.desc()).limit(200))
        for row in notes:
            result.append({"kind": "note", "id": row.id, "label": row.body[:180], "url": f"/deals/{deal.id}"})
        activities = list(await self.db.scalars(select(Activity).where((Activity.deal_id == deal.id) | ((Activity.deal_id.is_(None)) & (Activity.customer_id == deal.customer_id))).order_by(Activity.created_at.desc()).limit(200)))
        for row in activities:
            result.append({"kind": "activity", "id": row.id, "label": row.subject, "url": f"/activities?task={row.id}"})
        if activities:
            for row in await self.db.scalars(select(ActivityAttachment).where(ActivityAttachment.activity_id.in_([a.id for a in activities]))):
                result.append({"kind": "attachment", "id": row.id, "label": row.filename, "url": f"/activities?task={row.activity_id}"})
        for row in await self.db.scalars(select(Quote).where(Quote.customer_id == deal.customer_id, (Quote.deal_id == deal.id) | Quote.deal_id.is_(None)).order_by(Quote.created_at.desc()).limit(200)):
            result.append({"kind": "quote", "id": row.id, "label": row.quote_number, "url": f"/quotes/{row.id}"})
        messages = await self.db.execute(select(Message, Conversation).join(Conversation, Message.conversation_id == Conversation.id).where(Conversation.customer_id == deal.customer_id, Message.direction.in_(("in", "out"))).order_by(Message.created_at.desc()).limit(200))
        for row, conversation in messages:
            result.append({"kind": "message", "id": row.id, "label": conversation.subject, "url": f"/messages?c={conversation.id}"})
        return result

    async def add_evidence(self, deal_id, key, data, actor):
        deal = await self.deal(deal_id, lock=True)
        milestone = await self.milestone(deal, key)
        if deal.stage == DealStage.LOST:
            raise ConflictError("Reopen the opportunity to add evidence", "MCEM_LOST_READ_ONLY")
        if data.occurred_on > await self.today():
            raise ConflictError("Evidence cannot be dated in the future", "MCEM_EVIDENCE_DATE")
        if data.contact_id:
            person = await self.db.get(Contact, data.contact_id)
            if person is None or person.customer_id != deal.customer_id:
                raise ConflictError("Choose a contact at this customer", "CONTACT_CUSTOMER_MISMATCH")
        label = str(data.url) if data.kind == "link" else None
        if data.kind != "link":
            source = next((s for s in await self.sources(deal_id) if s["kind"] == data.kind and s["id"] == data.ref_id), None)
            if source is None:
                raise NotFoundError("Evidence must belong to this opportunity or its customer", "MCEM_EVIDENCE_NOT_FOUND")
            label = source["label"]
        row = McemEvidence(company_id=deal.company_id, milestone_id=milestone.id, kind=data.kind, ref_id=data.ref_id, url=str(data.url) if data.url else None, source_label=label[:255], explanation=data.explanation.strip(), occurred_on=data.occurred_on, contact_id=data.contact_id, added_by=actor.id)
        self.db.add(row)
        await self.db.flush()
        self.event(deal, actor.id, "evidence_added", {"key": key, "evidence": record(row)})
        if milestone.status == "confirmed":
            await self.invalidate(deal, {key}, actor.id, "New evidence added; review the confirmation")
        return await self.detail(deal_id)

    async def detail(self, deal_id):
        deal = await self.deal(deal_id)
        if not deal.mcem_enabled:
            return {"enabled": False}
        journey = await self.journey(deal)
        rows = await self.milestones(deal)
        evidence = list(await self.db.scalars(select(McemEvidence).where(McemEvidence.milestone_id.in_([m.id for m in rows.values()])).order_by(McemEvidence.created_at)))
        phase = pipeline_phase(deal.stage, rows.values())
        events = list(await self.db.scalars(select(McemEvent).where(McemEvent.deal_id == deal.id).order_by(McemEvent.created_at.desc(), McemEvent.id).limit(100)))
        if deal.stage == DealStage.LOST:
            last = next((e for e in events if e.kind == "stage_changed" and e.detail.get("to") == "lost"), None)
            phase = last.detail["phase"] if last else "Not recorded before MCEM was enabled"
        next_action = await self.db.scalar(select(Activity).where(Activity.deal_id == deal.id, Activity.done.is_(False)).order_by(Activity.due_date, Activity.due_time.nulls_last()).limit(1))
        expansions = list(await self.db.scalars(select(Deal).where(Deal.parent_deal_id == deal.id).order_by(Deal.created_at.desc())))
        return {"enabled": True, "phase": phase, "journey": record(journey), "milestones": [dict(record(rows[key]), label=label, phase=p, applicable=key != "renewal" or journey.recurring, evidence=[record(e) for e in evidence if e.milestone_id == rows[key].id]) for key, label, p in CATALOG],
                "readiness": {target: await self.issues(deal, target) for target in GATES}, "next_action": record(next_action) if next_action else None,
                "events": [record(e) for e in events], "expansions": [{"id": d.id, "title": d.title, "stage": d.stage.value, "value": d.value} for d in expansions]}

    async def expansion(self, deal_id, data, actor):
        deal = await self.deal(deal_id, lock=True)
        if deal.stage != DealStage.WON or not deal.mcem_enabled:
            raise ConflictError("Expansion starts from a won MCEM opportunity", "MCEM_EXPANSION_NOT_WON")
        from app.schemas.crm import DealCreate
        from app.services.deal_service import DealService
        new = await DealService(self.db).create_deal(DealCreate(title=data.title, customer_id=deal.customer_id, contact_id=deal.contact_id, owner_id=deal.owner_id or actor.id, value=data.value), actor.id)
        new.parent_deal_id = deal.id
        await self.db.flush()
        await self.enable(new.id, actor)
        self.event(deal, actor.id, "expansion_created", {"deal_id": new.id, "title": new.title})
        return {"id": new.id, "title": new.title}

    async def report(self):
        today = await self.today()
        deals = list(await self.db.scalars(select(Deal).where(Deal.mcem_enabled.is_(True)).order_by(Deal.updated_at.desc())))
        rows = list(await self.db.scalars(select(McemMilestone)))
        journeys = {j.deal_id: j for j in await self.db.scalars(select(McemJourney))}
        result = []
        for deal in deals:
            journey = journeys.get(deal.id)
            milestones = [m for m in rows if m.deal_id == deal.id]
            overdue = sum(m.due_date is not None and m.due_date < today and m.status != "confirmed" for m in milestones if m.key != "renewal" or (journey and journey.recurring)) if deal.stage != DealStage.LOST else 0
            renewal_done = any(m.key == "renewal" and m.status == "confirmed" and not m.needs_review for m in milestones)
            result.append({"id": deal.id, "title": deal.title, "stage": deal.stage.value, "phase": None if deal.stage == DealStage.LOST else pipeline_phase(deal.stage, milestones), "owner_id": deal.owner_id, "overdue_milestones": overdue, "needs_review": sum(m.needs_review for m in milestones), "journey_state": journey.state if journey else None, "next_review_date": journey.next_review_date if journey else None, "renewal_date": journey.renewal_date if journey and journey.recurring and not renewal_done else None})
        return {"opportunities": result, "overdue_milestones": sum(r["overdue_milestones"] for r in result), "reviews_due": sum(r["stage"] == "won" and r["next_review_date"] is not None and r["next_review_date"] <= today for r in result), "renewals_due": sum(r["stage"] == "won" and r["renewal_date"] is not None and r["renewal_date"] <= today for r in result)}

    async def history(self, deal_id, offset=0, limit=20):
        await self.deal(deal_id)
        rows = await self.db.scalars(select(McemEvent).where(McemEvent.deal_id == deal_id).order_by(McemEvent.created_at.desc(), McemEvent.id).offset(offset).limit(limit))
        return [record(row) for row in rows]

    async def remind(self, today):
        """Daily, deduplicated team reminders. Never customer email."""
        from app.services.notify import notify
        deals = list(await self.db.scalars(select(Deal).where(Deal.mcem_enabled.is_(True), Deal.stage != DealStage.LOST)))
        rows = list(await self.db.scalars(select(McemMilestone).where(McemMilestone.status != "confirmed", McemMilestone.due_date <= today)))
        journeys = {j.deal_id: j for j in await self.db.scalars(select(McemJourney))}
        sent = 0
        for deal in deals:
            journey = journeys.get(deal.id)
            if journey is None:
                continue
            owners = {}
            for row in rows:
                if row.deal_id != deal.id or row.owner_id is None or (row.key in POST_SALE and deal.stage != DealStage.WON) or (row.key == "renewal" and not journey.recurring):
                    continue
                owners.setdefault(row.owner_id, []).append(LABELS[row.key])
            if deal.stage == DealStage.WON:
                if journey.next_review_date and journey.next_review_date <= today and journey.account_owner_id:
                    owners.setdefault(journey.account_owner_id, []).append("Customer value review")
                renewal = (await self.milestones(deal)).get("renewal")
                if journey.recurring and journey.renewal_date and journey.renewal_date <= today and journey.account_owner_id and renewal and renewal.status != "confirmed":
                    owners.setdefault(journey.account_owner_id, []).append("Renewal decision")
            for user_id, labels in owners.items():
                user = await self.db.get(User, user_id)
                if user is None:
                    continue
                note = await notify(self.db, user, kind="mcem_due", title=f"Customer progress due: {deal.title}", body="; ".join(labels), link=f"/deals/{deal.id}", key=f"mcem:{deal.id}:{user_id}:{today.isoformat()}", email=False)
                sent += note is not None
        return sent
