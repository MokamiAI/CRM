import base64
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.exceptions import AppError
from app.schemas.documents import resolve_template
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
# The company's colour (Settings > Documents > accent) styles its emails;
# YGT's default where there's no company choice.
_templates.globals["accent"] = "#4f46e5"


def on_accent(hex_colour: str) -> str:
    """Readable text on the accent (WCAG relative luminance)."""
    try:
        r, g, b = (int(hex_colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#111827" if luminance > 0.36 else "#ffffff"


_templates.filters["on_accent"] = on_accent

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
    # A calendar invite (iCalendar text) and its METHOD (REQUEST or CANCEL):
    # sent as a calendar part so mail apps offer to add it to the calendar.
    calendar: str | None = None
    calendar_method: str = "REQUEST"
    # Files to attach, e.g. the invoice as a PDF: {"filename", "content"
    # (base64, so the email can travel to the worker as JSON), "mime"}.
    attachments: list[dict[str, str]] = field(default_factory=list)
    # The sender's display name for this email (e.g. "YGT Support"); the
    # address is always the configured one.
    from_name: str | None = None


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
    # The shared footer labels the company's VAT number with its document
    # settings, so every email from a company gets them, not just invoices.
    if "t" not in context and context.get("company") is not None:
        context["t"] = resolve_template(context["company"])
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
    message["From"] = formataddr((email.from_name or config.from_name, config.from_email))
    message["To"] = email.to
    for name, value in email.headers.items():
        message[name] = value
    if config.reply_to and "Reply-To" not in email.headers:
        message["Reply-To"] = config.reply_to
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    if email.calendar:
        # Gmail and Apple read the inline part; Outlook prefers the attachment.
        message.add_alternative(email.calendar, subtype="calendar", params={"method": email.calendar_method})
        message.add_attachment(email.calendar.encode(), maintype="text", subtype="calendar", filename="invite.ics", params={"method": email.calendar_method})
    for item in email.attachments:
        maintype, _, subtype = item.get("mime", "application/pdf").partition("/")
        message.add_attachment(base64.b64decode(item["content"]), maintype=maintype, subtype=subtype, filename=item["filename"])

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
