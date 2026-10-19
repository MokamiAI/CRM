"""Exercise the shared recipient query with real rows, including tenant boundaries."""
import uuid

import pytest
from sqlalchemy import create_engine, select, text

from app.models.customer import Customer
from app.services.contact_service import account_email_matches


@pytest.fixture
def recipients():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE customers (id TEXT, company_id TEXT, email TEXT)"))
        connection.execute(text("CREATE TABLE contacts (id TEXT, company_id TEXT, customer_id TEXT, email TEXT, is_primary BOOLEAN, created_at TEXT)"))
        company, customer = uuid.uuid4(), uuid.uuid4()
        connection.execute(text("INSERT INTO customers VALUES (:id, :company, :email)"),
                           dict(id=customer.hex, company=company.hex, email="company@example.com"))

        def add(email, primary=False, tenant=company):
            connection.execute(text("INSERT INTO contacts VALUES (:id, :company, :customer, :email, :primary, '2026-10-19')"),
                               dict(id=uuid.uuid4().hex, company=tenant.hex, customer=customer.hex, email=email, primary=primary))

        def address():
            return connection.scalar(select(Customer.recipient_email).where(Customer.id == customer))

        yield connection, add, address
    engine.dispose()


def test_primary_person_precedes_company_and_other_contacts(recipients):
    _, add, address = recipients
    add("other@example.com")
    add(" primary@example.com ", primary=True)
    assert address() == "primary@example.com"


def test_contact_with_no_company_email_is_reachable(recipients):
    connection, add, address = recipients
    connection.execute(text("UPDATE customers SET email = NULL"))
    add("buyer@example.com", primary=True)
    assert address() == "buyer@example.com"


def test_blank_contact_uses_other_person_then_legacy_company(recipients):
    _, add, address = recipients
    add("   ", primary=True)
    assert address() == "company@example.com"
    add("other@example.com")
    assert address() == "other@example.com"


def test_contacts_from_another_company_cannot_become_recipients(recipients):
    _, add, address = recipients
    add("foreign@example.com", primary=True, tenant=uuid.uuid4())
    assert address() == "company@example.com"


def test_missing_contact_and_company_email_returns_none(recipients):
    connection, _, address = recipients
    connection.execute(text("UPDATE customers SET email = ' '"))
    assert address() is None


def test_incoming_mail_recognizes_non_primary_contact_people(recipients):
    connection, add, _ = recipients
    add("primary@example.com", primary=True)
    add("other@example.com")
    assert connection.scalar(select(Customer.id).where(account_email_matches("OTHER@example.com")))
    assert connection.scalar(select(Customer.id).where(account_email_matches("unknown@example.com"))) is None
