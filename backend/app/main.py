from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    auth,
    billing,
    channels,
    company_settings,
    crm,
    custom_fields,
    customers,
    data,
    discovery,
    invoices,
    marketing,
    messaging,
    notifications,
    onboarding,
    payments,
    products,
    public,
    purchasing,
    quotes,
    recurring,
    reports,
    support,
    users,
)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    # The API reference is for development; production doesn't advertise it.
    openapi_url=None if settings.ENVIRONMENT == "production" else f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=None if settings.ENVIRONMENT == "production" else f"{settings.API_V1_PREFIX}/docs",
    redoc_url=None,
)

# Last added runs first: CORS outermost (so even a 429 carries CORS
# headers), then request ids and the activity log, then rate limits.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


# Working locally without Redis there's no worker or scheduler: check for
# due reminders here every 30 seconds instead (the server runs this job
# every minute in celery, see celery_app.py).
if settings.REDIS_URL.startswith("memory") and settings.ENVIRONMENT != "production":
    import asyncio
    import logging

    @app.on_event("startup")
    async def _local_reminder_loop() -> None:
        from app.tasks.notification_tasks import remind_all

        async def loop() -> None:
            while True:
                try:
                    await remind_all()
                except Exception:
                    logging.getLogger(__name__).exception("Local reminder check failed")
                await asyncio.sleep(30)

        app.state.reminder_loop = asyncio.create_task(loop())

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(customers.router, prefix=settings.API_V1_PREFIX)
app.include_router(products.router, prefix=settings.API_V1_PREFIX)
app.include_router(quotes.router, prefix=settings.API_V1_PREFIX)
app.include_router(purchasing.router, prefix=settings.API_V1_PREFIX)
app.include_router(invoices.router, prefix=settings.API_V1_PREFIX)
app.include_router(recurring.router, prefix=settings.API_V1_PREFIX)
app.include_router(discovery.router, prefix=settings.API_V1_PREFIX)
app.include_router(payments.router, prefix=settings.API_V1_PREFIX)
app.include_router(company_settings.router, prefix=settings.API_V1_PREFIX)
app.include_router(company_settings.profile_router, prefix=settings.API_V1_PREFIX)
app.include_router(crm.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
app.include_router(custom_fields.router, prefix=settings.API_V1_PREFIX)
app.include_router(marketing.router, prefix=settings.API_V1_PREFIX)
app.include_router(messaging.router, prefix=settings.API_V1_PREFIX)
app.include_router(channels.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(onboarding.router, prefix=settings.API_V1_PREFIX)
app.include_router(billing.router, prefix=settings.API_V1_PREFIX)
app.include_router(support.router, prefix=settings.API_V1_PREFIX)
app.include_router(data.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(public.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
