from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional, Any
from functools import lru_cache
import secrets


class Settings(BaseSettings):
    # App
    APP_NAME: str = "TAXUP"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # API
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_CACHE_TTL: int = 300  # 5 minutes

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if not v:
            return ["http://localhost:3000", "http://localhost:8080"]
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["http://localhost:3000", "http://localhost:8080"]
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Security - Digital Signature
    PRIVATE_KEY_PATH: str = "/run/secrets/private_key"
    PUBLIC_KEY_PATH: str = "/run/secrets/public_key"

    # Tax configuration
    DEFAULT_TAX_RATE: float = 0.18  # 18% TVA
    FRAUD_RISK_THRESHOLD: float = 0.75  # Score > 75% = fraud alert

    # Email / Notifications (Brevo)
    BREVO_API_KEY: Optional[str] = None
    EMAILS_FROM_EMAIL: str = "noreply@taxup.gn"
    EMAILS_FROM_NAME: str = "TAXUP — Plateforme Fiscale"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,  # ignore empty env vars → utilise la valeur par défaut
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
