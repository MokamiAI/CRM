from collections.abc import AsyncGenerator
from uuid import uuid4

from fastapi import Request
from fastapi.routing import APIRoute

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_url = make_url(settings.DATABASE_URL)
# Supabase's transaction pooler (port 6543) can hand a server connection to
# another client between transactions, so prepared statements are never
# cached and each gets a unique name, or two clients collide with
# DuplicatePreparedStatementError. That costs extra round trips per query,
# and the database is far away (Ireland, ~180 ms each way).
TRANSACTION_POOLER = _url.port == 6543

if TRANSACTION_POOLER:
    engine = create_async_engine(
        _url.update_query_dict({"prepared_statement_cache_size": "0"}),
        echo=settings.DEBUG,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4().hex}__",
        },
    )
else:
    # A session connection (Supabase's port 5432, or a plain PostgreSQL) keeps
    # its server connection, so queries are prepared once and reused: one
    # round trip per query. No ping on every checkout (another round trip);
    # connections are renewed every 5 minutes instead. The pool stays small:
    # Supabase limits session connections per project.
    engine = create_async_engine(
        _url,
        echo=settings.DEBUG,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        # Exposed so CommitBeforeResponseRoute can commit it on time.
        request.state.db = session
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class CommitBeforeResponseRoute(APIRoute):
    """Commits the request's session before the response goes out.

    get_db's own commit runs in dependency teardown, and from FastAPI 0.118
    teardown happens *after* the response has been sent. A client that
    creates a record and immediately asks for it (create a customer, then
    add a contact) could then get a 404 for something it was just told
    exists. Committing here, after the endpoint has succeeded but before
    the response is returned, gives read-your-writes on every FastAPI
    version; the later commit in get_db is then a no-op. If the endpoint
    raised, nothing is committed and get_db rolls back as before."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            response = await original(request)
            session = getattr(request.state, "db", None)
            if session is not None and session.in_transaction():
                await session.commit()
            return response

        return handler
