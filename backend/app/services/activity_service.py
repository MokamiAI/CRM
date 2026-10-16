import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.crm import Activity, Contact, Deal, Note, TaskUpdate
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.crm import ActivityCreate, ActivityUpdate, NoteCreate, TaskUpdateCreate
from app.services.notify import notify
from app.services.reminder_service import company_today

# Scopes for the activities list, matching how sales tools split the
# work queue: what's late, what's for today, what's coming, what's done.
SCOPES = ("overdue", "today", "upcoming", "done", "all")


async def _resolve_links(
    db: AsyncSession, customer_id: uuid.UUID | None, deal_id: uuid.UUID | None
) -> uuid.UUID | None:
    """An activity or note on a deal also belongs to the deal's customer,
    so it shows on the customer timeline too. Returns the customer id."""
    if deal_id is not None:
        deal = await db.get(Deal, deal_id)
        if deal is None:
            raise NotFoundError("Deal not found", "DEAL_NOT_FOUND")
        if customer_id is not None and customer_id != deal.customer_id:
            raise ConflictError("The deal belongs to a different customer", "DEAL_CUSTOMER_MISMATCH")
        return deal.customer_id
    if customer_id is not None and await db.get(Customer, customer_id) is None:
        raise NotFoundError("Customer not found", "CUSTOMER_NOT_FOUND")
    return customer_id


class ActivityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def today(self) -> date:
        settings_row = await CompanySettingsRepository(self.db).get_current()
        return company_today(settings_row.default_timezone)

    async def get_activity(self, activity_id: uuid.UUID) -> Activity:
        activity = await self.db.get(Activity, activity_id)
        if activity is None:
            raise NotFoundError("Activity not found", "ACTIVITY_NOT_FOUND")
        return activity

    async def list_activities(
        self,
        scope: str = "all",
        owner_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        deal_id: uuid.UUID | None = None,
        limit: int = 200,
        handed_out_by: uuid.UUID | None = None,
    ) -> list[Activity]:
        stmt = select(Activity)
        today = await self.today()
        if scope == "overdue":
            stmt = stmt.where(Activity.done.is_(False), Activity.due_date < today)
        elif scope == "today":
            stmt = stmt.where(Activity.done.is_(False), Activity.due_date == today)
        elif scope == "upcoming":
            stmt = stmt.where(Activity.done.is_(False), Activity.due_date > today)
        elif scope == "done":
            stmt = stmt.where(Activity.done.is_(True))
        if owner_id is not None:
            stmt = stmt.where(Activity.owner_id == owner_id)
        if handed_out_by is not None:
            # Given to someone else: what a manager is waiting on.
            stmt = stmt.where(Activity.created_by == handed_out_by, Activity.owner_id != handed_out_by)
        if customer_id is not None:
            stmt = stmt.where(Activity.customer_id == customer_id)
        if deal_id is not None:
            stmt = stmt.where(Activity.deal_id == deal_id)
        if scope == "done":
            stmt = stmt.order_by(Activity.done_at.desc())
        else:
            stmt = stmt.order_by(Activity.done, Activity.due_date, Activity.due_time.nulls_last())
        result = await self.db.execute(stmt.limit(limit))
        return list(result.scalars().all())

    async def counts(self, owner_id: uuid.UUID | None) -> dict[str, int]:
        """Open activity counts per scope, for nav badges and tabs."""
        today = await self.today()
        stmt = select(Activity.due_date).where(Activity.done.is_(False))
        if owner_id is not None:
            stmt = stmt.where(Activity.owner_id == owner_id)
        dates = (await self.db.execute(stmt)).scalars().all()
        return {
            "overdue": sum(d < today for d in dates),
            "today": sum(d == today for d in dates),
            "upcoming": sum(d > today for d in dates),
        }

    async def create_activity(self, data: ActivityCreate, user: User) -> Activity:
        customer_id = await _resolve_links(self.db, data.customer_id, data.deal_id)
        if data.contact_id is not None:
            contact = await self.db.get(Contact, data.contact_id)
            if contact is None or (customer_id and contact.customer_id != customer_id):
                raise ConflictError("The contact must belong to the same customer", "CONTACT_CUSTOMER_MISMATCH")
            customer_id = customer_id or contact.customer_id
        activity = Activity(
            **data.model_dump(exclude={"customer_id", "owner_id"}),
            customer_id=customer_id,
            owner_id=data.owner_id or user.id,
            created_by=user.id,
        )
        self.db.add(activity)
        await self.db.flush()
        if activity.owner_id != user.id:
            await self._tell_assignee(activity, user)
        return activity

    async def update_activity(self, activity_id: uuid.UUID, data: ActivityUpdate, user: User | None = None) -> Activity:
        activity = await self.get_activity(activity_id)
        changes = data.model_dump(exclude_unset=True)
        if "done" in changes and changes["done"] != activity.done:
            activity.done_at = datetime.now(timezone.utc) if changes["done"] else None
            # Ticked off (or un-ticked): the status follows.
            activity.status = "done" if changes["done"] else "todo"
        reassigned = "owner_id" in changes and changes["owner_id"] and changes["owner_id"] != activity.owner_id
        for field, value in changes.items():
            setattr(activity, field, value)
        await self.db.flush()
        if reassigned and user is not None and activity.owner_id != user.id:
            await self._tell_assignee(activity, user)
        return activity

    # ------------------------------------------------------------ team tasks

    async def _tell_assignee(self, activity: Activity, by: User) -> None:
        """Someone gave this to another person: tell them, once."""
        owner = await self.db.get(User, activity.owner_id)
        if owner is None:
            return
        when = activity.due_date.strftime("%d %b") + (f" at {activity.due_time.strftime('%H:%M')}" if activity.due_time else "")
        await notify(
            self.db, owner,
            kind="task_assigned",
            title=f"{by.full_name} assigned you: {activity.subject}",
            body=f"Due {when}." + (f" {activity.note}" if activity.note else ""),
            link=f"/activities?task={activity.id}",
            params={"by": by.full_name, "subject": activity.subject, "due": activity.due_date.isoformat(), "time": activity.due_time.strftime("%H:%M") if activity.due_time else None},
            key=f"assigned:{activity.id}:{activity.owner_id}",
        )

    async def list_updates(self, activity_id: uuid.UUID) -> list[TaskUpdate]:
        await self.get_activity(activity_id)
        rows = await self.db.scalars(select(TaskUpdate).where(TaskUpdate.activity_id == activity_id).order_by(TaskUpdate.created_at))
        return list(rows.all())

    async def add_update(self, activity_id: uuid.UUID, data: TaskUpdateCreate, user: User) -> TaskUpdate:
        """The person reports back: a status, a note, or both. Finishing or
        being stuck needs a word on what happened, for whoever's waiting."""
        activity = await self.get_activity(activity_id)
        note = (data.note or "").strip() or None
        if data.status is None and note is None:
            raise ConflictError("Choose a status or write a note", "TASK_UPDATE_EMPTY")
        if data.status in ("done", "blocked") and note is None:
            raise ConflictError("Please add a note saying what you did or what's in the way", "TASK_NOTE_REQUIRED")
        status = data.status if data.status and data.status != activity.status else None
        if status:
            activity.status = status
            if (status == "done") != activity.done:
                activity.done = status == "done"
                activity.done_at = datetime.now(timezone.utc) if activity.done else None
        update = TaskUpdate(activity_id=activity.id, author_id=user.id, status=status, note=note)
        self.db.add(update)
        await self.db.flush()
        # Whoever handed it out and whoever it's for hear about it (not the author).
        label = {"todo": "To do", "in_progress": "In progress", "blocked": "Blocked", "done": "Done"}
        for person_id in {activity.created_by, activity.owner_id} - {user.id, None}:
            person = await self.db.get(User, person_id)
            if person is None:
                continue
            headline = f"{user.full_name}: {label[status]}" if status else f"{user.full_name} added a note"
            await notify(
                self.db, person,
                kind="task_update",
                title=f"{headline} · {activity.subject}",
                body=note,
                link=f"/activities?task={activity.id}",
                params={"by": user.full_name, "subject": activity.subject, "status": status, "note": note},
                key=f"update:{update.id}",
            )
        return update

    async def delete_activity(self, activity_id: uuid.UUID) -> None:
        activity = await self.get_activity(activity_id)
        await self.db.delete(activity)
        await self.db.flush()


class NoteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_notes(self, customer_id: uuid.UUID | None, deal_id: uuid.UUID | None) -> list[Note]:
        stmt = select(Note)
        if deal_id is not None:
            stmt = stmt.where(Note.deal_id == deal_id)
        elif customer_id is not None:
            stmt = stmt.where(Note.customer_id == customer_id)
        result = await self.db.execute(stmt.order_by(Note.created_at.desc()).limit(200))
        return list(result.scalars().all())

    async def create_note(self, data: NoteCreate, user: User) -> Note:
        if data.customer_id is None and data.deal_id is None:
            raise ConflictError("A note needs a customer or a deal", "NOTE_NEEDS_PARENT")
        customer_id = await _resolve_links(self.db, data.customer_id, data.deal_id)
        note = Note(body=data.body, customer_id=customer_id, deal_id=data.deal_id, author_id=user.id)
        self.db.add(note)
        await self.db.flush()
        return note

    async def delete_note(self, note_id: uuid.UUID, user: User) -> None:
        note = await self.db.get(Note, note_id)
        if note is None:
            raise NotFoundError("Note not found", "NOTE_NOT_FOUND")
        # Notes are someone's words: only the author (or an admin) removes them.
        if note.author_id != user.id and user.role != UserRole.ADMIN:
            raise PermissionDeniedError("Only the author or an admin can delete this note")
        await self.db.delete(note)
        await self.db.flush()

