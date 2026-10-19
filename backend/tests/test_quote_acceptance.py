import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, decode_token
from app.services.quote_acceptance import acceptance_url, linked_quote, quote_recipient


def test_acceptance_link_is_scoped_to_quote_and_company():
    quote = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), updated_at=datetime.now(timezone.utc))
    token = acceptance_url(quote).rsplit('/', 1)[1]
    payload = decode_token(token)
    assert payload['type'] == 'quote-acceptance'
    assert payload['sub'] == str(quote.id)
    assert payload['company'] == str(quote.company_id)
    assert payload['version'] == quote.updated_at.isoformat()


@pytest.mark.asyncio
async def test_other_token_types_and_tampered_tokens_are_rejected_before_database_access():
    db = AsyncMock()
    for token in ('invalid-token', create_access_token(str(uuid.uuid4()), 'admin')):
        with pytest.raises(UnauthorizedError):
            await linked_quote(db, token)
    db.scalar.assert_not_called()


@pytest.mark.asyncio
async def test_deal_contact_email_takes_precedence():
    customer_id = uuid.uuid4()
    db = AsyncMock()
    db.get.side_effect = [SimpleNamespace(contact_id=uuid.uuid4()),
                          SimpleNamespace(customer_id=customer_id, email='buyer@example.com')]
    recipient = await quote_recipient(db, SimpleNamespace(deal_id=uuid.uuid4(), customer_id=customer_id),
                                      SimpleNamespace(email='accounts@example.com'))
    assert recipient == 'buyer@example.com'


@pytest.mark.asyncio
async def test_primary_contact_is_used_when_account_has_no_email():
    db = AsyncMock()
    db.scalar.return_value = 'primary@example.com'
    assert await quote_recipient(db, SimpleNamespace(deal_id=None, customer_id=uuid.uuid4()),
                                 SimpleNamespace(email=None, recipient_email='primary@example.com')) == 'primary@example.com'
