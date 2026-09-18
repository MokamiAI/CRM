from functools import lru_cache
from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "CRM & Invoice Management System"
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
    SMTP_FROM_NAME: str = "CRM System"

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
