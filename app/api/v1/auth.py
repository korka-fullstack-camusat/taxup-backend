from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, rate_limit
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin, UserUpdate, UserAdminResponse
from app.schemas.common import TokenResponse, MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Register a new user account."""
    return await AuthService.create_user(db, user_data)


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit),
):
    """Authenticate and receive JWT tokens."""
    return await AuthService.login(db, credentials.username, credentials.password)


@router.post("/refresh", response_model=dict)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using a valid refresh token."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return await AuthService.refresh_access_token(db, credentials.credentials)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_active_user),
):
    """Logout and blacklist the current token."""
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            exp = payload.get("exp", 0)
            await AuthService.logout(credentials.credentials, exp)
        except ValueError:
            pass
    return MessageResponse(message="Successfully logged out")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user profile."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    return await AuthService.update_user(db, current_user, update_data)


@router.post("/rotate-api-key", response_model=dict)
async def rotate_api_key(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Rotate the API key for the current user."""
    new_key = await AuthService.rotate_api_key(db, current_user)
    return {"api_key": new_key, "message": "API key rotated successfully"}
