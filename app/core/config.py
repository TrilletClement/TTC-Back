from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # fastapi-server/

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # App
    DEBUG: bool = False
    ENV: str = "prod"

    # Database
    DATABASE_URL: str

    # Security / JWT
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # Mail
    MAIL_USERNAME: str = "admin@trillet.be"
    MAIL_PASSWORD: str = "aUrbol,28,;"
    MAIL_FROM: str = "admin@trillet.be"
    MAIL_SERVER: str = "mail.b-kaiser.be"
    MAIL_PORT: int = 465
    MAIL_SSL_TLS: bool = True
    MAIL_STARTTLS: bool = False
    FRONTEND_URL: str = "https://transport.trillet.be"
    TURNSTILE_SECRET_KEY: str = "0x4AAAAAACynx6LG7GR6hr1VtUK9uyut8OE"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost",         # Important pour le Front Docker
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
