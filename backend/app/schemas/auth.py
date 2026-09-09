from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[uuid.UUID] = None
    phone: Optional[str] = Field(None, max_length=30)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=10, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ActivateRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class UserPublic(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    status: str
    is_superuser: bool
    designation: Optional[str] = None
    phone: Optional[str] = None
    primary_organization_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime


class MeResponse(UserPublic):
    roles: List[str] = []
    permissions: List[str] = []
    organization_name: Optional[str] = None


class UserUpdateSelf(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
