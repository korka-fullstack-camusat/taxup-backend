from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_roles
from app.models.user import UserRole
from app.core.redis import redis_client

router = APIRouter(prefix="/admin", tags=["Admin - Settings"])

_SETTINGS_KEY = "platform:settings"
_ONE_YEAR_TTL = 365 * 24 * 3600

_DEFAULTS: dict = {
    "fraud_threshold": 0.75,
    "max_transaction_amount": 10_000_000,
    "alert_email": "",
    "maintenance_mode": False,
    "auto_audit_enabled": True,
<<<<<<< HEAD
    "default_tax_rate": 0.18,
=======
>>>>>>> 661ee2d04c5667b767b22c745790395a7b678c89
}


class PlatformSettings(BaseModel):
    fraud_threshold: float = Field(0.75, ge=0.0, le=1.0)
    max_transaction_amount: int = Field(10_000_000, ge=0)
    alert_email: str = ""
    maintenance_mode: bool = False
    auto_audit_enabled: bool = True
<<<<<<< HEAD
    default_tax_rate: float = Field(0.18, ge=0.0, le=1.0)
=======
>>>>>>> 661ee2d04c5667b767b22c745790395a7b678c89


@router.get(
    "/settings",
    response_model=PlatformSettings,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
async def get_platform_settings():
    """Get platform-wide configuration settings (admin only)."""
    data = await redis_client.get(_SETTINGS_KEY)
    if data:
        return data
    return _DEFAULTS


@router.put(
    "/settings",
    response_model=PlatformSettings,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
async def update_platform_settings(settings: PlatformSettings):
    """Update platform-wide configuration settings (admin only)."""
    await redis_client.set(_SETTINGS_KEY, settings.model_dump(), ttl=_ONE_YEAR_TTL)
    return settings
