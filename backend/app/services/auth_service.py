from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import Roles
from app.core.security import (
    activation_expiry,
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_reset_expiry,
    refresh_token_expiry,
    validate_password_strength,
    verify_password,
)
from app.models.identity import Organization, OrganizationMember, PasswordResetToken, RefreshToken, Role, User, UserRole, UserStatus
from app.notifications.service import get_email_provider

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def password_version(user: User) -> int:
    """Millisecond timestamp of the last password change; embedded in access
    tokens so that any change invalidates previously issued tokens exactly."""
    return int(user.password_changed_at.timestamp() * 1000) if user.password_changed_at else 0


def get_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if not role:
        raise NotFoundError(f"Role {name} is not seeded")
    return role


def assign_role(db: Session, user: User, role_name: str, granted_by: Optional[User] = None) -> None:
    role = get_role(db, role_name)
    exists = db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=granted_by.id if granted_by else None))
        db.flush()


def register(db: Session, *, email: str, password: str, full_name: str, designation: Optional[str], organization_id: Optional[uuid.UUID], phone: Optional[str], request: Optional[Request] = None, auto_activate: bool = False) -> Tuple[User, Optional[str]]:
    email = email.lower().strip()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("An account with this email already exists")
    weak = validate_password_strength(password)
    if weak:
        raise ValidationFailed(weak)
    org = None
    if organization_id:
        org = db.get(Organization, organization_id)
        if not org or not org.is_active:
            raise ValidationFailed("Organization not found")
    user = User(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        designation=designation,
        phone=phone,
        primary_organization_id=org.id if org else None,
        status=UserStatus.ACTIVE if auto_activate else UserStatus.PENDING,
    )
    activation_token: Optional[str] = None
    if not auto_activate:
        activation_token = generate_opaque_token()
        user.activation_token_hash = hash_token(activation_token)
        user.activation_expires_at = activation_expiry()
    db.add(user)
    db.flush()
    assign_role(db, user, Roles.PUBLIC)
    if org:
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, member_role="member"))
    audit.record(db, "auth.register", user=user, resource_type="user", resource_id=user.id, request=request)
    if activation_token:
        link = f"{settings.frontend_base_url}/activate?token={activation_token}"
        get_email_provider().send(user.email, "Activate your Bhoomitra account", f"Welcome to Bhoomitra. Activate your account: {link}\n\nThe link expires in {settings.activation_token_expire_hours} hours.")
    db.commit()
    return user, activation_token


def activate(db: Session, token: str, request: Optional[Request] = None) -> User:
    h = hash_token(token)
    user = db.scalar(select(User).where(User.activation_token_hash == h))
    if not user or not user.activation_expires_at or user.activation_expires_at < _now():
        raise ValidationFailed("Activation link is invalid or has expired")
    user.status = UserStatus.ACTIVE
    user.activation_token_hash = None
    user.activation_expires_at = None
    audit.record(db, "auth.activate", user=user, resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return user


def _issue_refresh(db: Session, user: User, request: Optional[Request], family_id: Optional[uuid.UUID] = None) -> str:
    raw = generate_opaque_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=refresh_token_expiry(),
        user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
        ip_address=(request.client.host if request and request.client else None),
    )
    db.add(rt)
    db.flush()
    return raw


def login(db: Session, email: str, password: str, request: Optional[Request] = None) -> Tuple[User, str, str]:
    email = email.lower().strip()
    user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    generic = AuthError("Invalid email or password")
    if not user:
        verify_password(password, "$2b$12$invalidsaltinvalidsaltinvalidsaltinvalidsaltinvalidsalt12")
        audit.record(db, "auth.login", result="failure", detail={"email": email, "reason": "unknown_user"}, request=request, commit=True)
        raise generic
    if user.locked_until and user.locked_until > _now():
        audit.record(db, "auth.login", user=user, result="failure", detail={"reason": "locked"}, request=request, commit=True)
        raise AuthError("Account temporarily locked due to repeated failed logins. Try again later.", code="account_locked")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
        audit.record(db, "auth.login", user=user, result="failure", detail={"reason": "bad_password"}, request=request)
        db.commit()
        raise generic
    if user.status == UserStatus.PENDING:
        raise AuthError("Account is not activated yet. Check your email for the activation link.", code="account_pending")
    if user.status == UserStatus.DISABLED:
        audit.record(db, "auth.login", user=user, result="failure", detail={"reason": "disabled"}, request=request, commit=True)
        raise ForbiddenError("Account is disabled. Contact the platform administrator.", code="account_disabled")
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    refresh = _issue_refresh(db, user, request)
    access = create_access_token(str(user.id), {"email": user.email, "su": user.is_superuser, "pv": password_version(user)})
    audit.record(db, "auth.login", user=user, resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return user, access, refresh


def refresh(db: Session, raw_refresh: str, request: Optional[Request] = None) -> Tuple[User, str, str]:
    h = hash_token(raw_refresh)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == h))
    if not token:
        raise AuthError("Invalid refresh token")
    if token.revoked_at is not None:
        db.execute(update(RefreshToken).where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=_now()))
        audit.record(db, "auth.refresh", user=token.user, result="failure", detail={"reason": "reuse_detected", "family": str(token.family_id)}, request=request, commit=True)
        raise AuthError("Refresh token reuse detected; all sessions revoked", code="token_reuse")
    if token.expires_at < _now():
        raise AuthError("Refresh token expired", code="token_expired")
    user = token.user
    if user.status != UserStatus.ACTIVE or user.deleted_at is not None:
        raise AuthError("Account is not active", code="account_inactive")
    token.revoked_at = _now()
    new_raw = _issue_refresh(db, user, request, family_id=token.family_id)
    new_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_raw)))
    token.replaced_by = new_token.id if new_token else None
    access = create_access_token(str(user.id), {"email": user.email, "su": user.is_superuser, "pv": password_version(user)})
    db.commit()
    return user, access, new_raw


def logout(db: Session, raw_refresh: Optional[str], user: Optional[User], everywhere: bool = False, request: Optional[Request] = None) -> int:
    revoked = 0
    if everywhere and user:
        res = db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=_now()))
        revoked = res.rowcount or 0
    elif raw_refresh:
        token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh), RefreshToken.revoked_at.is_(None)))
        if token:
            token.revoked_at = _now()
            revoked = 1
    if user:
        audit.record(db, "auth.logout", user=user, detail={"revoked": revoked, "everywhere": everywhere}, request=request)
    db.commit()
    return revoked


def forgot_password(db: Session, email: str, request: Optional[Request] = None) -> Optional[str]:
    user = db.scalar(select(User).where(User.email == email.lower().strip(), User.deleted_at.is_(None)))
    if not user:
        return None
    raw = generate_opaque_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(raw), expires_at=password_reset_expiry()))
    audit.record(db, "auth.password_reset_requested", user=user, resource_type="user", resource_id=user.id, request=request)
    link = f"{settings.frontend_base_url}/reset-password?token={raw}"
    get_email_provider().send(user.email, "Reset your Bhoomitra password", f"Use this link to reset your password: {link}\n\nIt expires in {settings.password_reset_expire_minutes} minutes. If you did not request this, ignore this email.")
    db.commit()
    return raw


def reset_password(db: Session, token: str, new_password: str, request: Optional[Request] = None) -> User:
    weak = validate_password_strength(new_password)
    if weak:
        raise ValidationFailed(weak)
    prt = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    if not prt or prt.used_at is not None or prt.expires_at < _now():
        raise ValidationFailed("Reset link is invalid or has expired")
    user = db.get(User, prt.user_id)
    if not user:
        raise NotFoundError("User not found")
    user.password_hash = hash_password(new_password)
    user.password_changed_at = _now()
    user.failed_login_attempts = 0
    user.locked_until = None
    prt.used_at = _now()
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=_now()))
    audit.record(db, "auth.password_reset", user=user, resource_type="user", resource_id=user.id, request=request)
    db.commit()
    return user


def change_password(db: Session, user: User, current: str, new: str, request: Optional[Request] = None) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthError("Current password is incorrect")
    weak = validate_password_strength(new)
    if weak:
        raise ValidationFailed(weak)
    user.password_hash = hash_password(new)
    user.password_changed_at = _now()
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=_now()))
    audit.record(db, "auth.password_changed", user=user, resource_type="user", resource_id=user.id, request=request)
    db.commit()
