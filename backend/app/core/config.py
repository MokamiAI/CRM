import os
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AnyUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # YGT_ENV_FILE picks another settings file, e.g. .env.local for work on
    # a PC against a local database; the default is .env.
    model_config = SettingsConfigDict(env_file=os.environ.get("YGT_ENV_FILE", ".env"), extra="ignore")

    # App
    APP_NAME: str = "YGT"
    ENVIRONMENT: str = "development"
    # Sign-up checks that an email's domain receives mail (a DNS look-up).
    # None: on in production only, so tests and offline work don't need DNS.
    CHECK_EMAIL_DOMAINS: bool | None = None
    # Push messages to phones and computers (Web Push). Make a key pair once
    # (scripts/make_vapid_keys.py) and put both halves in the server's .env;
    # without them, notifications still go to the bell and by email.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:support@yougt.co.za"
    # Accounts made before the 48-hour email confirmation rule get their 48
    # hours from this moment (see services/verification_service.py).
    EMAIL_VERIFY_RULE_STARTED: datetime = datetime(2026, 10, 16, tzinfo=timezone.utc)
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
    SMTP_FROM_EMAIL: str | None = "billing@yougt.co.za"
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
    # Where new help desk tickets and Contact us messages are delivered: a
    # private inbox, never shown to anyone.
    SUPPORT_EMAIL: str | None = None
    # The support address people see: on the website, in the footer of
    # YGT's own (no-reply) emails, and as the organiser of session invites.
    # Defaults to SUPPORT_EMAIL.
    PUBLIC_SUPPORT_EMAIL: str | None = None
    # Discovery (Scale): free OpenStreetMap services. Both ask for a
    # descriptive User-Agent and light use; swap for a self-hosted mirror
    # if YGT grows.
    # Comma-separated: tried in order, the next one when a server is busy.
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter,https://overpass.private.coffee/api/interpreter,https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org/search"
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

    # Outside production the database must be on this machine, so testing
    # on a PC can never write to live data. Set true only on purpose.
    ALLOW_REMOTE_DATABASE: bool = False

    @model_validator(mode="after")
    def _local_database_outside_production(self):
        if self.ENVIRONMENT == "production" or self.ALLOW_REMOTE_DATABASE:
            return self
        for name in ("DATABASE_URL", "DATABASE_URL_MIGRATIONS"):
            host = urlsplit(getattr(self, name)).hostname or ""
            if host not in ("localhost", "127.0.0.1", "::1", "db", "postgres"):
                raise ValueError(
                    f"{name} points at {host}, but ENVIRONMENT is {self.ENVIRONMENT!r}: development must use a "
                    "local database. Use .env.local (YGT_ENV_FILE=.env.local), or set ALLOW_REMOTE_DATABASE=true on purpose."
                )
        return self

    @model_validator(mode="after")
    def _safe_in_production(self):
        """Refuses to start a production server on example or missing secrets:
        a known JWT_SECRET would let anyone forge a sign-in."""
        if self.ENVIRONMENT != "production":
            return self
        problems = []
        if len(self.JWT_SECRET) < 32 or "change-me" in self.JWT_SECRET:
            problems.append("JWT_SECRET must be a long random value")
        if "change-me" in self.INBOUND_EMAIL_SECRET:
            problems.append("INBOUND_EMAIL_SECRET must be a random value")
        if not self.CREDENTIALS_KEY:
            problems.append("CREDENTIALS_KEY must be set")
        if self.DEBUG:
            problems.append("DEBUG must be false")
        if problems:
            raise ValueError("Unsafe production settings: " + "; ".join(problems))
        return self

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
