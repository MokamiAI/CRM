"""Reads customer replies from a company's own mailbox over IMAP.

The company enters its mailbox login in Settings (Email > Incoming). A
beat task checks it every minute; each new email is parsed here and filed
by app/services/channel_service.py. Blocking (imaplib): call from a Celery
task or a threadpool, never directly in a request handler.
"""
import email
import imaplib
import re
from dataclasses import dataclass
from email import policy
from email.utils import getaddresses, parseaddr
from html import unescape

_CONNECT_TIMEOUT = 30


class MailboxError(Exception):
    """Login/connection problem; the message is safe to show the admin."""


@dataclass
class FetchedEmail:
    uid: int
    sender: str
    sender_name: str | None
    recipients: str
    subject: str
    text: str
    message_id: str | None
    references: str  # In-Reply-To + References, for finding the thread


def _connect(cfg: dict, password: str) -> imaplib.IMAP4:
    try:
        if cfg.get("use_ssl", True):
            imap = imaplib.IMAP4_SSL(cfg["host"], int(cfg.get("port") or 993), timeout=_CONNECT_TIMEOUT)
        else:
            imap = imaplib.IMAP4(cfg["host"], int(cfg.get("port") or 143), timeout=_CONNECT_TIMEOUT)
    except OSError as exc:
        raise MailboxError(f"Could not connect to {cfg.get('host')}: {exc}") from exc
    try:
        imap.login(cfg["username"], password)
    except imaplib.IMAP4.error as exc:
        raise MailboxError("The mailbox rejected the username or password. Gmail and Microsoft 365 need an app password.") from exc
    status, _ = imap.select(cfg.get("folder") or "INBOX", readonly=True)
    if status != "OK":
        raise MailboxError(f"Folder {cfg.get('folder') or 'INBOX'} not found")
    return imap


def test_mailbox(cfg: dict, password: str) -> str:
    imap = _connect(cfg, password)
    try:
        status, data = imap.uid("SEARCH", None, "ALL")
        count = len(data[0].split()) if status == "OK" and data and data[0] else 0
        return f"Connected. {count} emails in {cfg.get('folder') or 'INBOX'}."
    finally:
        imap.logout()


def _text_of(msg) -> str:
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        return part.get_content()
    part = msg.get_body(preferencelist=("html",))
    if part is None:
        return ""
    html = part.get_content()
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", html)
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def fetch_new(cfg: dict, password: str, last_uid: int | None, limit: int = 50) -> tuple[list[FetchedEmail], int]:
    """Emails newer than last_uid, and the new high-water mark. On the very
    first run (last_uid None) nothing is imported: we only start from now,
    so connecting a mailbox doesn't pull in years of old mail."""
    imap = _connect(cfg, password)
    try:
        status, data = imap.uid("SEARCH", None, "ALL")
        uids = [int(u) for u in (data[0].split() if status == "OK" and data and data[0] else [])]
        top = max(uids, default=0)
        if last_uid is None:
            return [], top
        new = sorted(u for u in uids if u > last_uid)[:limit]
        out: list[FetchedEmail] = []
        for uid in new:
            status, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")  # PEEK: don't mark as read
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            msg = email.message_from_bytes(parts[0][1], policy=policy.default)
            name, sender = parseaddr(msg.get("From", ""))
            recipients = ", ".join(addr for _, addr in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Delivered-To", [])))
            out.append(
                FetchedEmail(
                    uid=uid,
                    sender=sender.lower(),
                    sender_name=name or None,
                    recipients=recipients,
                    subject=str(msg.get("Subject", "") or ""),
                    text=_text_of(msg),
                    message_id=msg.get("Message-ID"),
                    references=f"{msg.get('In-Reply-To', '')} {msg.get('References', '')}",
                )
            )
        return out, max(new, default=last_uid)
    finally:
        imap.logout()
