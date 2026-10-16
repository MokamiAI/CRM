"""Files on activities and tasks.

Only everyday business files are taken (PDF, images, Office documents,
CSV and text), told apart by the file's extension and, where a format has
one, its first bytes. Web pages, SVG and programs are refused, and every
file is served as a download, so nothing uploaded can run in the app."""
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.exceptions import AppError, NotFoundError
from app.models.crm import ActivityAttachment
from app.models.user import User
from app.services.activity_service import ActivityService

MAX_BYTES = 10 * 1024 * 1024
MAX_FILES = 20

_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0"
# extension: (content type, first bytes it must start with, or None)
TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
    ".heic": ("image/heic", None),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (_ZIP,)),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (_ZIP,)),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", (_ZIP,)),
    ".doc": ("application/msword", (_OLE,)),
    ".xls": ("application/vnd.ms-excel", (_OLE,)),
    ".ppt": ("application/vnd.ms-powerpoint", (_OLE,)),
    ".odt": ("application/vnd.oasis.opendocument.text", (_ZIP,)),
    ".ods": ("application/vnd.oasis.opendocument.spreadsheet", (_ZIP,)),
    ".csv": ("text/csv", None),
    ".txt": ("text/plain", None),
}


def _clean_name(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '"<>|:*?')
    return (base or "file")[:200]


class AttachmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, activity_id: uuid.UUID) -> list[ActivityAttachment]:
        await ActivityService(self.db).get_activity(activity_id)
        stmt = select(ActivityAttachment).where(ActivityAttachment.activity_id == activity_id).order_by(ActivityAttachment.created_at)
        return list((await self.db.scalars(stmt)).all())

    async def add(self, activity_id: uuid.UUID, filename: str | None, content: bytes, user: User) -> ActivityAttachment:
        await ActivityService(self.db).get_activity(activity_id)
        name = _clean_name(filename)
        ext = os.path.splitext(name)[1].lower()
        kind = TYPES.get(ext)
        if kind is None:
            raise AppError("Attach a PDF, image, Office document, CSV or text file", "ATTACHMENT_BAD_TYPE", 422)
        content_type, magic = kind
        if magic and not content.startswith(magic):
            raise AppError("Attach a PDF, image, Office document, CSV or text file", "ATTACHMENT_BAD_TYPE", 422)
        if not content:
            raise AppError("That file is empty", "ATTACHMENT_EMPTY", 422)
        if len(content) > MAX_BYTES:
            raise AppError("Each file must be 10 MB or smaller", "ATTACHMENT_TOO_LARGE", 413)
        count = await self.db.scalar(select(func.count()).select_from(ActivityAttachment).where(ActivityAttachment.activity_id == activity_id))
        if count >= MAX_FILES:
            raise AppError(f"An activity can have up to {MAX_FILES} files", "ATTACHMENT_LIMIT", 422)
        row = ActivityAttachment(
            activity_id=activity_id, filename=name, content_type=content_type, size=len(content), data=content, uploaded_by=user.id
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def get(self, activity_id: uuid.UUID, attachment_id: uuid.UUID, with_data: bool = False) -> ActivityAttachment:
        stmt = select(ActivityAttachment).where(ActivityAttachment.id == attachment_id, ActivityAttachment.activity_id == activity_id)
        if with_data:
            stmt = stmt.options(undefer(ActivityAttachment.data))
        row = await self.db.scalar(stmt)
        if row is None:
            raise NotFoundError("File not found", "ATTACHMENT_NOT_FOUND")
        return row

    async def remove(self, activity_id: uuid.UUID, attachment_id: uuid.UUID) -> None:
        await self.db.delete(await self.get(activity_id, attachment_id))
        await self.db.flush()
