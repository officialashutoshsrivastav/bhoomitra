from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        password = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        if len(password.encode("utf-8")) > 72:
            password = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(subject: str, extra: Optional[Dict[str, Any]] = None, expires_minutes: Optional[int] = None) -> str:
    exp = _now() + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: Dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int(exp.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def generate_opaque_token(nbytes: int = 48) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def refresh_token_expiry() -> datetime:
    return _now() + timedelta(days=settings.refresh_token_expire_days)


def password_reset_expiry() -> datetime:
    return _now() + timedelta(minutes=settings.password_reset_expire_minutes)


def activation_expiry() -> datetime:
    return _now() + timedelta(hours=settings.activation_token_expire_hours)


def validate_password_strength(password: str) -> Optional[str]:
    if len(password) < 10:
        return "Password must be at least 10 characters long"
    if not any(c.isdigit() for c in password):
        return "Password must contain a digit"
    if not any(c.isalpha() for c in password):
        return "Password must contain a letter"
    if password.lower() in {"password12", "bhoomitra123", "1234567890"}:
        return "Password is too common"
    return None
