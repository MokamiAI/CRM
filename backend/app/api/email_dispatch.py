import logging

from celery import Task
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def commit_and_enqueue(db: AsyncSession, task: Task, *args) -> None:
    """Commits the request's transaction, then queues a Celery email task.

    The commit must come first: otherwise the worker can pick the task up
    before the invoice/payment row it reads is visible. (get_db's own
    commit at teardown is then a no-op.) Queueing failures, e.g. Redis
    being down, are logged rather than raised: the invoice really was sent
    and the payment really was recorded, so the request still succeeds."""
    await db.commit()
    try:
        # .delay() talks to Redis synchronously; keep it off the event loop.
        await run_in_threadpool(task.delay, *args)
    except Exception:
        logger.exception("Could not queue %s%r", task.name, args)


async def commit_and_enqueue_each(db: AsyncSession, task: Task, args_list: list[tuple]) -> None:
    """commit_and_enqueue for a batch: one commit, then one task per args
    tuple. A queueing failure skips that one task, not the rest."""
    await db.commit()
    for args in args_list:
        try:
            await run_in_threadpool(task.delay, *args)
        except Exception:
            logger.exception("Could not queue %s%r", task.name, args)
