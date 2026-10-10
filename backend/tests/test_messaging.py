from app.services.messaging_service import _TOKEN_RE, strip_quoted


def test_strips_gmail_style_quote():
    text = "Yes, Thursday works.\n\nThanks\n\nOn Mon, 6 Oct 2026 at 10:02, Zintos Trading <billing@x.com> wrote:\n> Can we meet Thursday?\n"
    assert strip_quoted(text) == "Yes, Thursday works.\n\nThanks"


def test_strips_outlook_style_quote():
    text = "Please send the invoice again.\n\n-----Original Message-----\nFrom: Zintos\nSent: Monday\n"
    assert strip_quoted(text) == "Please send the invoice again."


def test_drops_inline_quoted_lines():
    assert strip_quoted("> old line\nNew answer") == "New answer"


def test_keeps_text_when_everything_looks_quoted():
    # Better to show the whole thing than an empty message.
    assert strip_quoted("> only quoted") == "> only quoted"


def test_finds_thread_and_inbox_tokens_in_recipient_lists():
    m = _TOKEN_RE.search('"Zintos" <reply+AbC123_-xyz@inbound.example.com>, other@x.com')
    assert (m.group(1), m.group(2)) == ("reply", "AbC123_-xyz")
    m = _TOKEN_RE.search("INBOX+tok12345@inbound.example.com")
    assert (m.group(1).lower(), m.group(2)) == ("inbox", "tok12345")
    assert _TOKEN_RE.search("someone@example.com") is None
