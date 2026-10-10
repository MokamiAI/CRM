from collections.abc import AsyncGenerator

from fastapi import Request
from fastapi.routing import APIRoute

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    # Supabase's transaction-mode pooler does not support server-side
    # prepared statement caching across connections.
    connect_args={"statement_cache_size": 0},
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
