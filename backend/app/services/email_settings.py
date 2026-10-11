from dataclasses import dataclass

from app.core.config import settings
from app.core.crypto import decrypt
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
    # Where replies go when From can't be the company's own address.
    reply_to: str | None = None


def resolve_email_config(company: CompanySettings) -> EffectiveEmailConfig:
    """Merges the company's own SMTP configuration (set via PATCH /settings)
    over the server-wide SMTP_* env var defaults. A company that hasn't set
    smtp_host yet falls back to the shared server credentials in
    app/core/config.py. Sending itself is in app/services/email_service.py."""
    own_server = bool(company.smtp_host)
    name = company.sender_name or company.company_name or settings.SMTP_FROM_NAME
    if own_server or not settings.SMTP_FROM_EMAIL:
        from_email, reply_to = company.sender_email or settings.SMTP_FROM_EMAIL or "", None
    else:
        # On YGT's shared server, mail must come From YGT's own verified
        # address, or SPF/DMARC send it to spam. The company's name is shown,
        # and replies go to the company.
        from_email, reply_to = settings.SMTP_FROM_EMAIL, company.sender_email
    return EffectiveEmailConfig(
        host=company.smtp_host or settings.SMTP_HOST,
        port=company.smtp_port or settings.SMTP_PORT,
        username=company.smtp_username or settings.SMTP_USERNAME,
        password=decrypt(company.smtp_password) or settings.SMTP_PASSWORD,
        use_tls=company.smtp_use_tls if own_server else settings.SMTP_USE_TLS,
        from_email=from_email,
        from_name=name,
        reply_to=reply_to if reply_to and reply_to != from_email else None,
    )
