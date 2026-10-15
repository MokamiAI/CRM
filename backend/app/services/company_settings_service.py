import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.core.exceptions import AppError
from app.models.company_settings import CompanySettings
from app.repositories.company_settings_repository import CompanySettingsRepository
from app.schemas.company_settings import CompanySettingsUpdate
from app.services.email_service import clean_signature


MAX_LOGO_BYTES = 500 * 1024


def _image_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


class CompanySettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.company_settings = CompanySettingsRepository(db)

    async def get_settings(self) -> CompanySettings:
        return await self.company_settings.get_current()

    async def save_logo(self, content: bytes) -> CompanySettings:
        """Keeps an uploaded logo and points logo_url at it. PNG, JPEG or
        WebP only, told apart by their first bytes (never trusting the
        file name); SVG is refused, as it can carry scripts."""
        kind = _image_type(content)
        if kind is None:
            raise AppError("Use a PNG, JPG or WebP image", "LOGO_BAD_TYPE", 422)
        if len(content) > MAX_LOGO_BYTES:
            raise AppError("The logo must be 500 KB or smaller", "LOGO_TOO_LARGE", 413)
        row = await self.company_settings.get_current()
        row.logo_image, row.logo_content_type = content, kind
        version = hashlib.sha256(content).hexdigest()[:10]
        # The site's own address (Caddy passes /api to the backend): the one
        # emails already link to, so it is right wherever YGT runs.
        row.logo_url = f"{settings.FRONTEND_URL.rstrip('/')}{settings.API_V1_PREFIX}/public/logo/{row.id}?v={version}"
        return await self.company_settings.save(row)

    async def remove_logo(self) -> CompanySettings:
        row = await self.company_settings.get_current()
        row.logo_image = row.logo_content_type = row.logo_url = None
        return await self.company_settings.save(row)

    async def update_settings(self, data: CompanySettingsUpdate) -> CompanySettings:
        row = await self.company_settings.get_current()
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "smtp_password" and value:
                value = encrypt(value)  # stored encrypted; see app/core/crypto.py
            if field == "email_signature":
                value = clean_signature(value)
            setattr(row, field, value)
        return await self.company_settings.save(row)
