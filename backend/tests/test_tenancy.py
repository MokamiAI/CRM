import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContextError, get_tenant, set_system, set_tenant
from app.models.customer import Customer
from app.models.marketing import Segment


def _flush(session: Session) -> None:
    # before_flush runs before any connection is needed, so the guards can
    # be exercised without a database.
    session.dispatch.before_flush(session, None, None)


def test_query_without_context_is_refused():
    with Session() as session, pytest.raises(TenantContextError):
        session.execute(select(Customer))


def test_get_tenant_without_context_is_refused():
    with Session() as session, pytest.raises(TenantContextError):
        get_tenant(session)


def test_new_rows_are_stamped_with_the_tenant():
    company = uuid.uuid4()
    with Session() as session:
        set_tenant(session, company)
        segment = Segment(name="VIP", rules=[])
        session.add(segment)
        _flush(session)
        assert segment.company_id == company


def test_writing_into_another_company_is_refused():
    with Session() as session:
        set_tenant(session, uuid.uuid4())
        session.add(Segment(name="VIP", rules=[], company_id=uuid.uuid4()))
        with pytest.raises(TenantContextError, match="another company"):
            _flush(session)


def test_system_writes_must_name_their_company():
    with Session() as session:
        set_system(session)
        session.add(Segment(name="VIP", rules=[]))
        with pytest.raises(TenantContextError, match="no company_id"):
            _flush(session)

