import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.exceptions import AppError
from app.services.email_settings import EffectiveEmailConfig

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

# HTML templates are autoescaped (customer names, notes, etc. are user
# input); .txt templates are not, since plain text has nothing to escape.
_templates = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

_SMTP_TIMEOUT_SECONDS = 30


class EmailNotConfiguredError(AppError):
    def __init__(self, message: str = "Outgoing email is not configured: set an SMTP host and sender email in Settings"):
        super().__init__(message, "EMAIL_NOT_CONFIGURED")


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    html: str
    text: str
    # Extra headers, e.g. List-Unsubscribe on marketing email.
    headers: dict[str, str] = field(default_factory=dict)


def clean_signature(value: str | None) -> str | None:
    """A signature as stored: plain text, tidy line endings, no blank lines
    at either end. Blank means none."""
    if value is None:
        return None
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = "\n".join(lines).strip("\n")
    return text or None


def render_email(template: str, to: str, subject: str, **context) -> OutgoingEmail:
    """Renders templates/emails/<template>.html and .txt into one message,
    so every email has both an HTML body and a plain-text fallback."""
    return OutgoingEmail(
        to=to,
        subject=subject,
        html=_templates.get_template(f"{template}.html").render(subject=subject, **context),
        text=_templates.get_template(f"{template}.txt").render(subject=subject, **context),
    )


def send_email(config: EffectiveEmailConfig, email: OutgoingEmail) -> None:
    """Sends one message over SMTP. Blocking: call it from a Celery worker
    or a threadpool, never directly inside an async request handler.

    Port 465 uses implicit TLS (SMTP_SSL); any other port uses plain SMTP,
    upgraded with STARTTLS when use_tls is set (the usual setup on 587)."""
    if not config.host or not config.from_email:
        raise EmailNotConfiguredError()

    message = EmailMessage()
    message["Subject"] = email.subject
    message["From"] = formataddr((config.from_name, config.from_email))
    message["To"] = email.to
    for name, value in email.headers.items():
        message[name] = value
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")

    tls_context = ssl.create_default_context()
    if config.port == 465:
        smtp = smtplib.SMTP_SSL(config.host, config.port, timeout=_SMTP_TIMEOUT_SECONDS, context=tls_context)
    else:
        smtp = smtplib.SMTP(config.host, config.port, timeout=_SMTP_TIMEOUT_SECONDS)

    with smtp:
        if config.port != 465 and config.use_tls:
            smtp.starttls(context=tls_context)
        if config.username:
            smtp.login(config.username, config.password or "")
        smtp.send_message(message)
