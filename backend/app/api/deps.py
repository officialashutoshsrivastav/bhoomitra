from __future__ import annotations

import uuid
from typing import Callable, List, Optional, Set

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AuthError, ForbiddenError
from app.core.logging import user_id_ctx
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import decode_token
from app.db.database import get_db
from app.models.identity import Permission, Role, RolePermission, User, UserRole, UserStatus

bearer = HTTPBearer(auto_error=False)


def load_user_permissions(db: Session, user: User) -> Set[str]:
    if user.is_superuser:
        from app.core.permissions import ALL_PERMISSIONS

        return set(ALL_PERMISSIONS)
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    perms = set(db.scalars(stmt).all())
    return perms


def user_role_names(db: Session, user: User) -> List[str]:
    stmt = select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    return list(db.scalars(stmt).all())


def get_current_user_optional(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)) -> Optional[User]:
    if not creds:
        return None
    try:
        payload = decode_token(creds.credentials, "access")
    except jwt.ExpiredSignatureError:
        raise AuthError("Access token expired", code="token_expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid access token")
    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except ValueError:
        raise AuthError("Invalid token subject")
    user = db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise AuthError("User not found")
    if user.status != UserStatus.ACTIVE:
        raise AuthError("Account is not active", code="account_inactive")
    current_pv = int(user.password_changed_at.timestamp() * 1000) if user.password_changed_at else 0
    if "pv" in payload:
        if payload["pv"] != current_pv:
            raise AuthError("Token invalidated by password change", code="token_expired")
    elif user.password_changed_at and payload.get("iat") and user.password_changed_at.timestamp() > payload["iat"] + 1:
        raise AuthError("Token invalidated by password change", code="token_expired")
    request.state.user = user
    request.state.permissions = load_user_permissions(db, user)
    user_id_ctx.set(str(user.id))
    return user


def get_current_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise AuthError("Authentication required")
    return user


def get_permissions(request: Request, user: User = Depends(get_current_user)) -> Set[str]:
    return getattr(request.state, "permissions", set())


def require_permissions(*codes: str, any_of: bool = False) -> Callable:
    def dependency(request: Request, user: User = Depends(get_current_user), perms: Set[str] = Depends(get_permissions)) -> User:
        needed = set(codes)
        ok = bool(needed & perms) if any_of else needed.issubset(perms)
        if not ok:
            raise ForbiddenError("You do not have permission to perform this action", details={"required": sorted(needed), "mode": "any" if any_of else "all"})
        return user

    return dependency


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise ForbiddenError("Super administrator access required")
    return user


def has_permission(request: Request, code: str) -> bool:
    return code in getattr(request.state, "permissions", set())


def default_role_permissions(role_name: str) -> Set[str]:
    return ROLE_PERMISSIONS.get(role_name, set())
