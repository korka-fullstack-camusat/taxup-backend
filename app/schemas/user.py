import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.models.user import UserRole
import re


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.CITOYEN
    phone_number: Optional[str] = None
    organization: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        # Normalize: strip spaces, hyphens, dots, parentheses
        cleaned = re.sub(r"[\s\-\.\(\)]", "", v)
        if not re.match(r"^\+?[0-9]{8,15}$", cleaned):
            raise ValueError("Num\u00e9ro de t\u00e9l\u00e9phone invalide (ex\u202f: +221771001001)")
        return cleaned


class UserCreate(UserBase):
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.+-]{3,50}$", v):
            raise ValueError("Username must be 3-50 chars, alphanumeric, _ . + or - only")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caract\u00e8res")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    organization: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserAdminResponse(UserResponse):
    api_key: Optional[str] = None


class UserAdminUpdate(BaseModel):
    """Schema for admin updating any user field."""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    organization: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        # Normalize: strip spaces, hyphens, dots, parentheses
        cleaned = re.sub(r"[\s\-\.\(\)]", "", v)
        if not re.match(r"^\+?[0-9]{8,15}$", cleaned):
            raise ValueError("Num\u00e9ro de t\u00e9l\u00e9phone invalide (ex\u202f: +221771001001)")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caract\u00e8res")
        return v


class PaginatedUsers(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int
