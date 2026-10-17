"""Relationship-management API: contacts, deals, activities, notes,
record timelines, global search and the team directory.

Reads are open to every signed-in role; writes need ADMIN/MANAGER/STAFF,
matching the customer and invoice routes. Deleting a deal (it takes its
activities and notes with it) is ADMIN/MANAGER only."""
import uuid

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.models.enums import UserRole
from app.models.quote import Quote
from app.models.user import User
from app.schemas.crm import (
    AttachmentOut,
    TaskUpdateCreate,
    TaskUpdateOut,
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    DealCreate,
    DealOut,
    DealUpdate,
    NoteCreate,
    NoteOut,
    SearchHit,
    TimelineItem,
    UserBrief,
)
from app.schemas.quote import QuoteOut
from app.services.activity_service import SCOPES, ActivityService, NoteService
from app.services.attachment_service import MAX_BYTES, AttachmentService
from app.services.contact_service import ContactService
from app.services.deal_service import DealService
from app.services.timeline_service import SearchService, TimelineService

router = APIRouter(route_class=CommitBeforeResponseRoute, tags=["crm"])

_can_write = require_role(UserRole.ADMIN, UserRole.MANAGER, UserRole.STAFF)
_can_manage = require_role(UserRole.ADMIN, UserRole.MANAGER)


# ---------- Contacts ----------


@router.get("/customers/{customer_id}/contacts", response_model=list[ContactOut])
async def list_contacts(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await ContactService(db).list_contacts(customer_id)


@router.post("/customers/{customer_id}/contacts", response_model=ContactOut, status_code=201)
async def create_contact(
    customer_id: uuid.UUID, data: ContactCreate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    return await ContactService(db).create_contact(customer_id, data)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID, data: ContactUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    return await ContactService(db).update_contact(contact_id, data)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await ContactService(db).delete_contact(contact_id)


@router.get("/customers/{customer_id}/timeline", response_model=list[TimelineItem])
async def customer_timeline(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await TimelineService(db).customer_timeline(customer_id)


# ---------- Deals ----------


@router.get("/deals", response_model=list[DealOut])
async def list_deals(
    status_filter: str = Query("open", alias="status", pattern="^(open|won|lost|all)$"),
    mine: bool = Query(False, description="Only deals owned by the current user"),
    customer_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await DealService(db).list_deals(
        status=status_filter, owner_id=current_user.id if mine else None, customer_id=customer_id
    )


@router.post("/deals", response_model=DealOut, status_code=201)
async def create_deal(data: DealCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)):
    service = DealService(db)
    deal = await service.create_deal(data, created_by_id=current_user.id)
    return (await service.with_next_activity([deal]))[0]


@router.get("/deals/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    service = DealService(db)
    return (await service.with_next_activity([await service.get_deal(deal_id)]))[0]


@router.patch("/deals/{deal_id}", response_model=DealOut)
async def update_deal(
    deal_id: uuid.UUID, data: DealUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)
):
    service = DealService(db)
    return (await service.with_next_activity([await service.update_deal(deal_id, data, current_user.id)]))[0]


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_manage)):
    await DealService(db).delete_deal(deal_id)


@router.get("/deals/{deal_id}/timeline", response_model=list[TimelineItem])
async def deal_timeline(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await TimelineService(db).deal_timeline(deal_id)


@router.get("/deals/{deal_id}/quotes", response_model=list[QuoteOut])
async def deal_quotes(deal_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    await DealService(db).get_deal(deal_id)
    result = await db.execute(
        select(Quote).options(selectinload(Quote.items)).where(Quote.deal_id == deal_id).order_by(Quote.created_at.desc())
    )
    return list(result.scalars().all())


# ---------- Activities ----------


@router.get("/activities", response_model=list[ActivityOut])
async def list_activities(
    scope: str = Query("all", pattern=f"^({'|'.join(SCOPES)})$"),
    mine: bool = Query(False, description="Only activities assigned to the current user"),
    handed_out: bool = Query(False, description="Only tasks the current user gave to someone else"),
    customer_id: uuid.UUID | None = Query(default=None),
    deal_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await ActivityService(db).list_activities(
        scope=scope,
        owner_id=current_user.id if mine else None,
        handed_out_by=current_user.id if handed_out else None,
        customer_id=customer_id,
        deal_id=deal_id,
    )


@router.get("/activities/counts", response_model=dict[str, int])
async def activity_counts(
    mine: bool = Query(True), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return await ActivityService(db).counts(owner_id=current_user.id if mine else None)


@router.post("/activities", response_model=ActivityOut, status_code=201)
async def create_activity(data: ActivityCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)):
    return await ActivityService(db).create_activity(data, current_user)


@router.patch("/activities/{activity_id}", response_model=ActivityOut)
async def update_activity(
    activity_id: uuid.UUID, data: ActivityUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)
):
    return await ActivityService(db).update_activity(activity_id, data, current_user)


@router.get("/activities/{activity_id}/updates", response_model=list[TaskUpdateOut])
async def list_task_updates(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """What people did on this task, oldest first."""
    return await ActivityService(db).list_updates(activity_id)


@router.post("/activities/{activity_id}/updates", response_model=TaskUpdateOut, status_code=201)
async def add_task_update(
    activity_id: uuid.UUID, data: TaskUpdateCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)
):
    """Report back on a task: a status (to do, in progress, blocked, done)
    and/or a note; tells whoever assigned it."""
    return await ActivityService(db).add_update(activity_id, data, current_user)


@router.get("/activities/{activity_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await AttachmentService(db).list(activity_id)


@router.post("/activities/{activity_id}/attachments", response_model=AttachmentOut, status_code=201)
async def add_attachment(
    activity_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)
):
    """A file for the activity (10 MB max)."""
    content = await file.read(MAX_BYTES + 1)
    return await AttachmentService(db).add(activity_id, file.filename, content, current_user)


@router.get("/activities/{activity_id}/attachments/{attachment_id}", include_in_schema=False)
async def download_attachment(
    activity_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    row = await AttachmentService(db).get(activity_id, attachment_id, with_data=True)
    return Response(
        row.data,
        media_type=row.content_type,
        headers={
            # Always a download: an uploaded file never runs as part of the app.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/activities/{activity_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    activity_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)
):
    await AttachmentService(db).remove(activity_id, attachment_id)


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(_can_write)):
    await ActivityService(db).delete_activity(activity_id)


# ---------- Notes ----------


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(
    customer_id: uuid.UUID | None = Query(default=None),
    deal_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await NoteService(db).list_notes(customer_id, deal_id)


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(data: NoteCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)):
    return await NoteService(db).create_note(data, current_user)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(_can_write)):
    await NoteService(db).delete_note(note_id, current_user)


# ---------- Search & team ----------


@router.get("/search", response_model=list[SearchHit])
async def search(q: str = Query(..., min_length=1, max_length=100), db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    return await SearchService(db).search(q)


@router.get("/team", response_model=list[UserBrief])
async def team(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Active users, name only: for owner pickers and avatars. The full
    user list (emails, roles) stays ADMIN-only under /users."""
    result = await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.full_name))
    return list(result.scalars().all())
