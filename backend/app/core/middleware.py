"""Request middleware: request ids, the activity (audit) log, the error log
and rate limiting. Logs are written after the response, on their own
database session, so they never slow down or break the request itself."""
import asyncio
import logging
import time
import traceback
import uuid
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# Provider webhooks and tracking pixels: high volume, not people's actions.
_NOT_AUDITED = ("/public/paystack/", "/public/channels/", "/public/inbound/", "/public/m/", "/auth/refresh")
_background: set[asyncio.Task] = set()


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _later(coro) -> None:
    """Runs a log write after the response without awaiting it."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _write(row) -> None:
    from app.core.database import AsyncSessionLocal
    from app.core.tenancy import set_system

    try:
        async with AsyncSessionLocal() as session:
            set_system(session)
            session.add(row)
            await session.commit()
    except Exception:  # never let logging take anything down
        logger.exception("Could not write %s", type(row).__name__)


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def record_error(request: Request | None, exc: BaseException, source: str = "api", **extra) -> None:
    """Stores an unexpected error for the admin site's error log."""
    from app.models.platform import ErrorLog

    state = getattr(request, "state", None)
    row = ErrorLog(
        source=source,
        company_id=_uuid(getattr(state, "company_id", None) or extra.get("company_id")),
        user_id=_uuid(getattr(state, "user_id", None)),
        request_id=getattr(state, "request_id", None),
        method=request.method if request else None,
        path=str(request.url.path)[:500] if request else extra.get("path"),
        error_type=type(exc).__name__,
        message=str(exc)[:4000],
        traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-20000:],
    )
    _later(_write(row))


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gives every request an id (returned as X-Request-ID, and shown with
    errors so people can quote it in a support ticket), and records each
    change in the activity log."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        path = request.url.path.removeprefix(settings.API_V1_PREFIX)
        if request.method in _MUTATING and request.url.path.startswith(settings.API_V1_PREFIX) and not path.startswith(_NOT_AUDITED):
            self._audit(request, response.status_code, path)
        return response

    @staticmethod
    def _audit(request: Request, status_code: int, path: str) -> None:
        from app.models.platform import AuditEvent

        state = request.state
        company_id = _uuid(getattr(state, "company_id", None))
        actor = getattr(state, "actor_email", None)
        if company_id is None and actor is None:
            return  # anonymous (e.g. a failed sign-in with no account)
        route = request.scope.get("route")
        template = getattr(route, "path", path).removeprefix(settings.API_V1_PREFIX)
        params = request.scope.get("path_params") or {}
        entity = next((str(v) for v in params.values() if _uuid(v)), None)
        _later(
            _write(
                AuditEvent(
                    company_id=company_id,
                    user_id=_uuid(getattr(state, "user_id", None)),
                    actor_email=actor,
                    method=request.method,
                    route=template[:300],
                    entity_id=entity,
                    status_code=status_code,
                    ip=client_ip(request)[:64],
                )
            )
        )


# ---------------------------------------------------------------- rate limits

# (path prefix, methods, limit, window seconds). First match wins; anything
# else under the API gets the general limit. Webhooks are never limited:
# providers retry, and their requests are verified by signature.
_RULES = [
    ("/public/paystack/", None, None, 0),
    ("/public/channels/", None, None, 0),
    ("/public/inbound/", None, None, 0),
    ("/auth/login", {"POST"}, 10, 300),
    ("/auth/register", {"POST"}, 5, 3600),
    ("/auth/forgot-password", {"POST"}, 5, 3600),
    ("/auth/reset-password", {"POST"}, 10, 3600),
    ("/public/contact", {"POST"}, 5, 3600),
    ("/imports/", {"POST"}, 20, 3600),
]
_GENERAL = (300, 60)


class _MemoryCounter:
    """Fixed windows per key, in this process."""

    def __init__(self):
        self._hits: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    async def hit(self, key: str, window: int) -> tuple[int, int]:
        now = time.monotonic()
        count, started = self._hits[key]
        if now - started >= window:
            count, started = 0, now
        count += 1
        self._hits[key] = (count, started)
        if len(self._hits) > 50_000:  # keep memory bounded
            cutoff = now - 3600
            for k in [k for k, (_, s) in self._hits.items() if s < cutoff]:
                del self._hits[k]
        return count, int(window - (now - started)) + 1


class _RedisCounter:
    def __init__(self, url: str):
        import redis.asyncio as redis

        self._redis = redis.from_url(url)

    async def hit(self, key: str, window: int) -> tuple[int, int]:
        bucket = f"rl:{key}:{int(time.time() // window)}"
        async with self._redis.pipeline(transaction=True) as pipe:
            count, _ = await pipe.incr(bucket).expire(bucket, window).execute()
        return int(count), window - int(time.time() % window)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.counter = _RedisCounter(settings.REDIS_URL) if settings.RATE_LIMIT_STORAGE == "redis" else _MemoryCounter()

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED or not request.url.path.startswith(settings.API_V1_PREFIX) or request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path.removeprefix(settings.API_V1_PREFIX)
        rule = next((r for r in _RULES if path.startswith(r[0]) and (r[1] is None or request.method in r[1])), None)
        if rule and rule[2] is None:
            return await call_next(request)
        limit, window = (rule[2], rule[3]) if rule else _GENERAL
        # Signed-in requests count per token, so an office behind one
        # address isn't limited as a single person.
        who = request.headers.get("authorization", "")[-24:] or client_ip(request)
        key = f"{rule[0] if rule else 'api'}:{who}"
        try:
            count, retry_after = await self.counter.hit(key, window)
        except Exception:  # a broken limiter must not take the API down
            logger.exception("Rate limiter unavailable")
            return await call_next(request)
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"success": False, "message": "Too many requests. Please wait a moment and try again.", "error_code": "RATE_LIMITED"},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
