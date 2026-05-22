from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, computed_field
from typing import List
from pathlib import Path

# Project root is three levels up from this file:
# config.py → core → app → fastapi-server → PROJECT_ROOT
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",   # .env also contains Docker/frontend vars not used by FastAPI
    )

    # App
    DEBUG: bool = False
    ENV: str = "local"

    # Database — credentials are the single source of truth.
    # DATABASE_URL is derived so it never needs to be set manually.
    POSTGRES_USER: str = "mylocaldb"
    POSTGRES_PASSWORD: str = "mylocaldb"
    POSTGRES_DB: str = "mylocaldb"
    DB_HOST: str = "localhost"   # override to "db" inside Docker

    @computed_field  # type: ignore[misc]
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.DB_HOST}:5432/{self.POSTGRES_DB}"
        )

    # Security / JWT
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    DEPLOY_SECRET: str = Field(...)

    # External APIs
    STIB_API_KEY: str = Field(...)
    TEC_API_KEY: str = ""
    TURNSTILE_SECRET_KEY: str = Field(...)

    # Mail
    MAIL_USERNAME: str = Field(...)
    MAIL_PASSWORD: str = Field(...)
    MAIL_FROM: str = Field(...)
    MAIL_SERVER: str = Field(...)
    MAIL_PORT: int = 465
    MAIL_SSL_TLS: bool = True
    MAIL_STARTTLS: bool = False

    # Stripe
    STRIPE_SECRET_KEY: str = Field(...)
    STRIPE_WEBHOOK_SECRET: str = Field(...)

    # URLs
    # Set to http://localhost:4200 locally, https://transport.trillet.be in production
    FRONTEND_URL: str = Field(...)
    API_BASE_URL: str = "http://localhost:8000"

    # Firmware storage — mount a volume here in Docker so files survive redeploys
    FIRMWARE_DIR: str = "/data/firmware"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    @computed_field  # type: ignore[misc]
    @property
    def GOOGLE_REDIRECT_URI(self) -> str:
        return f"{self.API_BASE_URL}/api/auth/google/callback"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:4200",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:4200",
        "http://127.0.0.1:8000",
        "https://transport.trillet.be",
        "http://192.168.14.13",
        "http://192.168.14.13:4200",
    ]

settings = Settings()
