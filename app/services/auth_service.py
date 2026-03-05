import uuid
import secrets
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token
)
from app.core.redis import redis_client


class AuthService:

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        # Check uniqueness
        existing = await db.execute(
            select(User).where(
                (User.username == user_data.username) | (User.email == user_data.email)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email already registered",
            )

        user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            role=user_data.role,
            phone_number=user_data.phone_number,
            organization=user_data.organization,
            api_key=secrets.token_urlsafe(32),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> User:
        user = await AuthService.get_user_by_username(db, username)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
        return user

    @staticmethod
    async def login(db: AsyncSession, username: str, password: str) -> dict:
        user = await AuthService.authenticate(db, username, password)
        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        if await redis_client.is_token_blacklisted(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
        user_id = payload.get("sub")
        user = await AuthService.get_user_by_id(db, uuid.UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        new_access_token = create_access_token(subject=str(user.id))
        return {"access_token": new_access_token, "token_type": "bearer"}

    @staticmethod
    async def logout(token: str, token_exp: int):
        from datetime import datetime, timezone
        import time
        remaining = max(0, token_exp - int(time.time()))
        await redis_client.blacklist_token(token, remaining)

    @staticmethod
    async def update_user(
        db: AsyncSession, user: User, update_data: UserUpdate
    ) -> User:
        for field, value in update_data.model_dump(exclude_none=True).items():
            setattr(user, field, value)
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def rotate_api_key(db: AsyncSession, user: User) -> str:
        new_key = secrets.token_urlsafe(32)
        user.api_key = new_key
        await db.flush()
        return new_key
