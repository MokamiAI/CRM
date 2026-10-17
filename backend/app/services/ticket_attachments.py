"""Private ticket files, using the same validation as activity attachments."""
import os
from urllib.parse import quote

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.core.exceptions import AppError, NotFoundError
from app.models.platform import TicketAttachment
from app.services.attachment_service import MAX_BYTES, TYPES, _clean_name

MAX_FILES = 5
MAX_TOTAL = 20 * 1024 * 1024


async def read_files(files):
    if len(files) > MAX_FILES:
        raise AppError("Attach up to 5 files", "ATTACHMENT_LIMIT", 422)
    result = []
    total = 0
    for file in files:
        content = await file.read(MAX_BYTES + 1)
        name = _clean_name(file.filename)
        kind = TYPES.get(os.path.splitext(name)[1].lower())
        if not kind or (kind[1] and not content.startswith(kind[1])):
            raise AppError("Attach a PDF, image, Office document, CSV or text file", "ATTACHMENT_BAD_TYPE", 422)
        if not content:
            raise AppError("That file is empty", "ATTACHMENT_EMPTY", 422)
        total += len(content)
        if len(content) > MAX_BYTES or total > MAX_TOTAL:
            raise AppError("Each file must be 10 MB or smaller, and all files together at most 20 MB", "ATTACHMENT_TOO_LARGE", 413)
        result.append({"filename": name, "content_type": kind[0], "size": len(content), "data": content})
    return result


async def list_files(db, ticket_id):
    return list(await db.scalars(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id).order_by(TicketAttachment.created_at)))


async def download(db, ticket_id, attachment_id):
    row = await db.scalar(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id, TicketAttachment.id == attachment_id).options(undefer(TicketAttachment.data)))
    if row is None:
        raise NotFoundError("File not found", "ATTACHMENT_NOT_FOUND")
    return Response(row.data, media_type=row.content_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename)}",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, no-store",
    })
