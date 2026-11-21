"""Saved documents are named client (or supplier) first, then the number,
with only the characters Windows refuses swapped out."""
from app.services.document_service import document_filename, safe_filename


def test_client_name_then_number():
    assert document_filename("Sizwe Builders", "INV-0053") == "Sizwe Builders - INV-0053"
    assert document_filename("Smith & Sons (Pty) Ltd", "QUO-0008") == "Smith & Sons (Pty) Ltd - QUO-0008"
    assert document_filename("Zoë's Bakery", "PO-0004") == "Zoë's Bakery - PO-0004"


def test_no_client_name_leaves_the_number():
    assert document_filename(None, "INV-0001") == "INV-0001"
    assert document_filename("   ", "INV-0001") == "INV-0001"


def test_characters_windows_refuses_are_replaced():
    assert document_filename("A/B Builders", "INV-0053") == "A-B Builders - INV-0053"
    assert safe_filename('Back\\slash: "x"? <y>|*') == "Back-slash- -x-- -y---"
    assert safe_filename("tabs\tand\nnewlines") == "tabs-and-newlines"
    assert safe_filename("...") == "document"
    assert len(safe_filename("x" * 400)) == 150
