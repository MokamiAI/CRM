import smtplib

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_role
from app.core.database import CommitBeforeResponseRoute
from app.core.exceptions import AppError
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.company_settings import (
    CompanyProfileOut,
    CompanySettingsOut,
    CompanySettingsUpdate,
    TestEmailRequest,
    TestEmailResult,
)
from app.schemas.documents import DocumentTemplate, PreviewRequest, resolve_template
from app.services.company_settings_service import CompanySettingsService
from app.services.document_service import DocumentService
from app.services.email_service import send_email
from app.services.notification_service import NotificationService

_require_admin = require_role(UserRole.ADMIN)

router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/settings", tags=["settings"], dependencies=[Depends(_require_admin)])

# Any signed-in user: name/currency/logo only, never the SMTP settings.
profile_router = APIRouter(route_class=CommitBeforeResponseRoute, prefix="/company", tags=["settings"], dependencies=[Depends(get_current_user)])


@profile_router.get("", response_model=CompanyProfileOut)
async def get_company_profile(db: AsyncSession = Depends(get_db)):
    return await CompanySettingsService(db).get_settings()


@router.get("", response_model=CompanySettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    row = await CompanySettingsService(db).get_settings()
    return CompanySettingsOut.from_model(row)


@router.patch("", response_model=CompanySettingsOut)
async def update_settings(data: CompanySettingsUpdate, db: AsyncSession = Depends(get_db)):
    row = await CompanySettingsService(db).update_settings(data)
    return CompanySettingsOut.from_model(row)


@router.post("/test-email", response_model=TestEmailResult)
async def send_test_email(
    data: TestEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Sends a test message with the saved email settings, synchronously,
    so the admin sees immediately whether the SMTP configuration works
    (customer emails go through Celery, where failures only show in logs)."""
    service = NotificationService(db)
    config = await service.email_config()
    email = await service.compose_test_email(data.to or current_user.email)
    try:
        await run_in_threadpool(send_email, config, email)
    except smtplib.SMTPAuthenticationError:
        raise AppError("The mail server rejected the SMTP username or password", "EMAIL_AUTH_FAILED", 502)
    except OSError as exc:
        # smtplib.SMTPException is an OSError, as are connection/TLS errors.
        raise AppError(f"Could not send the test email: {exc}", "EMAIL_SEND_FAILED", 502)
    return TestEmailResult(sent_to=email.to)


# ---------- Settings > Documents: how invoices, quotes and statements look ----------


@router.get("/documents", response_model=DocumentTemplate)
async def get_document_template(db: AsyncSession = Depends(get_db)):
    return resolve_template(await CompanySettingsService(db).get_settings())


@router.put("/documents", response_model=DocumentTemplate)
async def save_document_template(data: DocumentTemplate, db: AsyncSession = Depends(get_db)):
    row = await CompanySettingsService(db).get_settings()
    row.document_template = data.model_dump()
    await db.flush()
    return data


@router.post("/documents/preview", response_class=HTMLResponse)
async def preview_document_template(data: PreviewRequest, db: AsyncSession = Depends(get_db)):
    """The unsaved template applied to sample records, for the live preview."""
    return HTMLResponse(await DocumentService(db).preview_html(data.template, data.kind))
