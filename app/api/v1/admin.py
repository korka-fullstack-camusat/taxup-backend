import uuid
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.api.deps import get_current_active_user, require_roles
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserAdminUpdate, UserResponse, PaginatedUsers
from app.services.email_service import (
    send_account_created_email,
    send_account_activated_email,
    send_account_deactivated_email,
)

router = APIRouter(prefix="/users", tags=["Admin - User Management"])

_admin_only = Depends(require_roles(UserRole.ADMIN))


@router.get("", response_model=PaginatedUsers)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = _admin_only,
):
    """List all users with optional search/filter and pagination (admin only)."""
    query = select(User)

    if search:
        like = f"%{search}%"
        query = query.where(
            or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.full_name.ilike(like),
            )
        )

    if role:
        try:
            role_enum = UserRole(role)
            query = query.where(User.role == role_enum)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid role: {role}")

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedUsers(items=list(users), total=total, page=page, page_size=page_size, pages=pages)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = _admin_only,
):
    """Create a new user account (admin only). Sends welcome email with credentials."""
    from app.services.auth_service import AuthService

    plain_password = user_data.password
    new_user = await AuthService.create_user(db, user_data)

    # Send welcome email with credentials (non-blocking)
    await send_account_created_email(
        to_email=new_user.email,
        full_name=new_user.full_name,
        username=new_user.username,
        password=plain_password,
        role=new_user.role.value,
    )

    return new_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = _admin_only,
):
    """Get a user by ID (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    update_data: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = _admin_only,
):
    """Update any field of a user (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check email uniqueness if changing
    if update_data.email and update_data.email != user.email:
        existing = await db.execute(select(User).where(User.email == update_data.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    for field, value in update_data.model_dump(exclude_none=True).items():
        if field == "password":
            user.hashed_password = get_password_hash(value)
        else:
            setattr(user, field, value)

    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Delete a user permanently (admin only)."""
    if current_admin.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.delete(user)
    await db.flush()


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = _admin_only,
):
    """Activate a user account (admin only). Sends reactivation email."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = True
    await db.flush()
    await db.refresh(user)

    # Notify user
    await send_account_activated_email(
        to_email=user.email,
        full_name=user.full_name,
    )

    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Deactivate a user account (admin only). Sends deactivation email."""
    if current_admin.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await db.flush()
    await db.refresh(user)

    # Notify user
    await send_account_deactivated_email(
        to_email=user.email,
        full_name=user.full_name,
    )

    return user
