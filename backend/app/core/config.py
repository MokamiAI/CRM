from functools import lru_cache
from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "YGT"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database (Supabase Postgres)
    # DATABASE_URL: async app traffic, routed through Supabase's pgbouncer
    #   transaction-mode pooler (port 6543). Used by SQLAlchemy at runtime.
    DATABASE_URL: str
    # DATABASE_URL_MIGRATIONS: direct/session connection (port 5432), used
    #   only by Alembic. pgbouncer transaction mode does not reliably
    #   support the DDL + prepared statements Alembic issues.
    DATABASE_URL_MIGRATIONS: str

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Email
    EMAIL_PROVIDER: str = "smtp"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "YGT"
    # STARTTLS on port 587 (port 465 always uses TLS). Off only for a local test server.
    SMTP_USE_TLS: bool = True

    # Public base URL of this API, used in links inside emails (unsubscribe,
    # open tracking) that customers' mail clients call without signing in.
    PUBLIC_API_URL: str = "http://localhost:8000"

    # Key that encrypts credentials companies enter in Settings (Fernet key:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").
    # Unset in development: derived from JWT_SECRET.
    CREDENTIALS_KEY: str | None = None
    # Testing only: send WhatsApp/SMS API calls to this base URL (a local
    # mock) instead of the real providers. Never set in production.
    CHANNEL_API_OVERRIDE: str | None = None

    # Two-way customer email. Outgoing messages set Reply-To to
    # reply+<thread token>@INBOUND_EMAIL_DOMAIN; the mail provider's inbound
    # webhook (Mailgun Routes, SendGrid Inbound Parse, Postmark Inbound...)
    # posts replies to /api/v1/public/inbound/email with this secret.
    INBOUND_EMAIL_DOMAIN: str = "inbound.localhost"
    INBOUND_EMAIL_SECRET: str = "change-me-inbound-secret"

    # Subscriptions, paid through YGT's own Paystack account (Paystack
    # dashboard > Settings > API Keys & Webhooks). Set the webhook URL there
    # to <PUBLIC_API_URL>/api/v1/public/paystack/webhook. Unset: the plans
    # still show, but checkout says online payments aren't set up yet.
    PAYSTACK_SECRET_KEY: str | None = None
    # Testing only: a local mock instead of api.paystack.co.
    PAYSTACK_API_BASE: str = "https://api.paystack.co"
    # Where the web app lives; Paystack sends people back here after paying.
    FRONTEND_URL: str = "http://localhost:5173"
    # New companies try the Grow plan free for this many days.
    TRIAL_DAYS: int = 14

    # ---- YGT's own team (the admin site) ----
    # Comma-separated emails of people who may open /admin. They sign in
    # with their normal YGT account.
    PLATFORM_ADMIN_EMAILS: str = ""
    # Where new help desk tickets and Contact us messages are emailed, and
    # the sender of YGT's own emails (password resets, ticket replies,
    # booking invites). Sent with the SMTP_* settings above.
    SUPPORT_EMAIL: str | None = None
    # The calendar address that session bookings are sent to as invites
    # (e.g. your Google Calendar Gmail address). Defaults to SUPPORT_EMAIL.
    BOOKING_CALENDAR_EMAIL: str | None = None

    # ---- Rate limiting ----
    # memory: per server process (fine for one server); redis: shared
    # across processes and servers, using REDIS_URL.
    RATE_LIMIT_STORAGE: str = "memory"
    RATE_LIMIT_ENABLED: bool = True
    # Behind a proxy (Caddy, Nginx, a platform's load balancer) the client's
    # address is in X-Forwarded-For; only trust it when that's true.
    TRUST_PROXY_HEADERS: bool = False

    @property
    def platform_admins(self) -> set[str]:
        return {e.strip().lower() for e in self.PLATFORM_ADMIN_EMAILS.split(",") if e.strip()}

    # Company defaults (seed values; overridden by company_settings table)
    COMPANY_NAME: str = "My Company"
    DEFAULT_CURRENCY: str = "ZAR"
    DEFAULT_TIMEZONE: str = "Africa/Johannesburg"

    # CORS
    # capacitor://localhost (iOS) and https://localhost (Android) are the
    # default origins a Capacitor-wrapped mobile build sends its API
    # requests from.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "capacitor://localhost",
        "https://localhost",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
