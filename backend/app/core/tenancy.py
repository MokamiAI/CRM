"""Multi-tenancy: every business ("company") sees only its own rows.

Tenant-owned models inherit TenantMixin (a company_id column). Each
database session carries a tenant context in session.info:

  * a company id  - every ORM SELECT/UPDATE/DELETE on a tenant model is
                    automatically filtered to that company, and new rows are
                    stamped with it on flush;
  * SYSTEM        - no filtering; for code that legitimately spans companies
                    (sign-in by email, background jobs that loop over
                    companies, public links that carry their own token).

A session with no context at all refuses to query anything, so a code path
that forgot to say which company it is acting for fails loudly instead of
quietly returning every company's data.
"""
import uuid

from sqlalchemy import ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, declared_attr, mapped_column, with_loader_criteria

_KEY = "tenant"


class _System:
    def __repr__(self) -> str:
        return "SYSTEM"


SYSTEM = _System()

# Execution option for the rare query that must look across every company
# from inside one, e.g. "is this email already a login anywhere?".
ALL_TENANTS = "all_tenants"


class TenantContextError(RuntimeError):
    """Raised when tenant data is touched without a tenant context."""


class TenantMixin:
    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("company_settings.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


def _session(session) -> Session:
    # Accept an AsyncSession too; events live on its underlying Session.
    return getattr(session, "sync_session", session)


def set_tenant(session, company_id: uuid.UUID) -> None:
    _session(session).info[_KEY] = company_id


def set_system(session) -> None:
    _session(session).info[_KEY] = SYSTEM


def get_tenant(session) -> uuid.UUID | None:
    """The current company id, or None in SYSTEM mode."""
    value = _session(session).info.get(_KEY)
    if value is None:
        raise TenantContextError("No tenant context on this session")
    return None if value is SYSTEM else value


def current_company_id(session) -> uuid.UUID:
    company_id = get_tenant(session)
    if company_id is None:
        raise TenantContextError("This operation needs a company context, not SYSTEM")
    return company_id


@event.listens_for(Session, "do_orm_execute")
def _filter_by_tenant(state: ORMExecuteState) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get(ALL_TENANTS):
        return
    value = state.session.info.get(_KEY)
    if value is None:
        raise TenantContextError(
            "Query without a tenant context: call set_tenant() or set_system() on the session first"
        )
    if value is SYSTEM:
        return
    state.statement = state.statement.options(
        with_loader_criteria(TenantMixin, lambda cls: cls.company_id == value, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _stamp_and_guard(session: Session, _flush_context, _instances) -> None:
    value = session.info.get(_KEY)
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, TenantMixin):
            continue
        if value is None:
            raise TenantContextError("Writing tenant data without a tenant context")
        if value is SYSTEM:
            if obj.company_id is None:
                raise TenantContextError(f"{type(obj).__name__} has no company_id")
            continue
        if obj.company_id is None:
            obj.company_id = value
        elif obj.company_id != value:
            raise TenantContextError(f"{type(obj).__name__} belongs to another company")
