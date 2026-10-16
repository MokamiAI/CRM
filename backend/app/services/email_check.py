"""Is this an email address someone can actually receive mail at?

Only the confirmation link proves it: no server can be sure a mailbox
exists without sending to it (and "pinging" mailboxes gets a sender
blocked as spam). Before sending, two cheap checks catch most mistakes:
the domain must be set up to receive mail (a typo like gmial.com, or a
made-up domain, isn't), and throwaway inboxes aren't accepted.
"""
import asyncio

from email_validator import EmailNotValidError, validate_email

from app.core.config import settings
from app.core.exceptions import AppError

# Throwaway-inbox services: anyone can read them, so they prove nothing.
DISPOSABLE = frozenset(
    {
        "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "sharklasers.com",
        "grr.la", "10minutemail.com", "10minutemail.net", "temp-mail.org", "tempmail.com", "tempmail.net",
        "tempmailo.com", "temp-mail.io", "yopmail.com", "yopmail.net", "trashmail.com", "trashmail.de",
        "getnada.com", "nada.email", "dispostable.com", "maildrop.cc", "throwawaymail.com", "mailnesia.com",
        "mintemail.com", "fakeinbox.com", "emailondeck.com", "mohmal.com", "burnermail.io", "moakt.com",
        "tempail.com", "mailcatch.com", "spamgourmet.com", "33mail.com", "inboxkitten.com", "minuteinbox.com",
    }
)


async def ensure_deliverable(email: str) -> None:
    """Raises if the address can't be a real, lasting inbox."""
    domain = email.rsplit("@", 1)[-1].lower()
    if domain in DISPOSABLE:
        raise AppError("Please use your own email address, not a temporary one.", "EMAIL_DISPOSABLE")
    check = settings.CHECK_EMAIL_DOMAINS
    if not (check if check is not None else settings.ENVIRONMENT == "production"):
        return
    try:
        # A DNS look-up for the domain's mail servers; off the event loop.
        await asyncio.to_thread(validate_email, email, check_deliverability=True, timeout=5)
    except EmailNotValidError:
        raise AppError("We can't send email to this address. Please check it for typos.", "EMAIL_UNDELIVERABLE")
    except Exception:  # DNS trouble on our side: don't turn a real person away
        return
