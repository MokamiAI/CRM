import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.database import engine

T = TypeVar("T")


def run_async(fn: Callable[[], Awaitable[T]]) -> T:
    """Runs an async DB job from a (sync) Celery task.

    Each call gets a fresh event loop via asyncio.run, but the SQLAlchemy
    engine is module-global, and asyncpg connections are bound to the loop
    that opened them. Disposing the pool afterwards stops the next task
    from picking up a connection tied to a now-closed loop."""

    async def _run() -> T:
        try:
            return await fn()
        finally:
            await engine.dispose()

    return asyncio.run(_run())
