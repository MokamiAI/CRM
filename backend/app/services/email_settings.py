from dataclasses import dataclass

from app.core.config import settings
from app.models.company_settings import CompanySettings


@dataclass(frozen=True)
class EffectiveEmailConfig:
    host: str | None
    port: int
    username: str | None
    password: str | None
    use_tls: bool
    from_email: str
    from_name: str


def resolve_email_config(company: CompanySettings) -> EffectiveEmailConfig:
    """Merges the company's own SMTP configuration (set via PATCH /settings)
    over the server-wide SMTP_* env var defaults. A company that hasn't set
    smtp_host yet falls back to the shared server credentials in
    app/core/config.py; the sending logic itself lands in Phase 10."""
    return EffectiveEmailConfig(
        host=company.smtp_host or settings.SMTP_HOST,
        port=company.smtp_port or settings.SMTP_PORT,
        username=company.smtp_username or settings.SMTP_USERNAME,
        password=company.smtp_password or settings.SMTP_PASSWORD,
        use_tls=company.smtp_use_tls,
        from_email=company.sender_email or settings.SMTP_FROM_EMAIL or "",
        from_name=company.sender_name or settings.SMTP_FROM_NAME,
    )
