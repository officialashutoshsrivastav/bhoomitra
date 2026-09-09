from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_permissions, user_role_names
from app.core.config import settings
from app.core.exceptions import AuthError
from app.db.database import get_db
from app.models.identity import Organization, User
from app.schemas.auth import (
    ActivateRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
    UserUpdateSelf,
)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "bhoomitra_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path=f"{settings.api_v1_prefix}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, domain=settings.cookie_domain, path=f"{settings.api_v1_prefix}/auth")


def _token_response(access: str, refresh: str, include_refresh: bool) -> TokenResponse:
    return TokenResponse(access_token=access, expires_in=settings.access_token_expire_minutes * 60, refresh_token=refresh if include_refresh else None)


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    user, token = auth_service.register(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        designation=payload.designation,
        organization_id=payload.organization_id,
        phone=payload.phone,
        request=request,
        auto_activate=settings.app_env in {"development", "test"} and not settings.is_production,
    )
    detail = {"user_id": str(user.id), "status": user.status.value}
    if token and settings.app_env in {"development", "test"}:
        detail["activation_token"] = token
    return Message(message="Registration successful", detail=detail)


@router.post("/activate", response_model=Message)
def activate(payload: ActivateRequest, request: Request, db: Session = Depends(get_db)):
    user = auth_service.activate(db, payload.token, request)
    return Message(message="Account activated", detail={"user_id": str(user.id)})


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user, access, refresh = auth_service.login(db, payload.email, payload.password, request)
    _set_refresh_cookie(response, refresh)
    return _token_response(access, refresh, include_refresh=True)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, payload: Optional[RefreshRequest] = None, db: Session = Depends(get_db)):
    raw = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AuthError("Refresh token missing")
    if not payload or not payload.refresh_token:
        # cookie flow: require a custom header so cross-site form posts cannot mint tokens
        if request.headers.get("x-requested-with", "").lower() != "xmlhttprequest":
            raise AuthError("Missing X-Requested-With header for cookie refresh", code="csrf")
    user, access, new_refresh = auth_service.refresh(db, raw, request)
    _set_refresh_cookie(response, new_refresh)
    return _token_response(access, new_refresh, include_refresh=bool(payload and payload.refresh_token))


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, payload: Optional[RefreshRequest] = None, everywhere: bool = False, db: Session = Depends(get_db)):
    raw = (payload.refresh_token if payload and payload.refresh_token else None) or request.cookies.get(REFRESH_COOKIE)
    user = None
    try:
        from app.api.deps import bearer, get_current_user_optional  # noqa

        creds = request.headers.get("authorization")
        if creds and creds.lower().startswith("bearer "):
            from app.core.security import decode_token
            import uuid as _uuid

            payload_tok = decode_token(creds.split(" ", 1)[1], "access")
            user = db.get(User, _uuid.UUID(payload_tok["sub"]))
    except Exception:
        user = None
    revoked = auth_service.logout(db, raw, user, everywhere=everywhere, request=request)
    _clear_refresh_cookie(response)
    return Message(message="Logged out", detail={"revoked_sessions": revoked})


@router.post("/password/forgot", response_model=Message)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    token = auth_service.forgot_password(db, payload.email, request)
    detail = {"reset_token": token} if token and settings.app_env in {"development", "test"} else None
    return Message(message="If the email exists, a reset link has been sent", detail=detail)


@router.post("/password/reset", response_model=Message)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    auth_service.reset_password(db, payload.token, payload.new_password, request)
    return Message(message="Password has been reset. Please log in again.")


@router.post("/password/change", response_model=Message)
def change_password(payload: ChangePasswordRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    auth_service.change_password(db, user, payload.current_password, payload.new_password, request)
    return Message(message="Password changed. Other sessions were signed out.")


@router.get("/me", response_model=MeResponse)
def me(request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    org_name = None
    if user.primary_organization_id:
        org_name = db.scalar(select(Organization.name).where(Organization.id == user.primary_organization_id))
    base = UserPublic.model_validate(user).model_dump()
    base["status"] = user.status.value
    return MeResponse(**base, roles=user_role_names(db, user), permissions=sorted(perms), organization_name=org_name)


@router.patch("/me", response_model=UserPublic)
def update_me(payload: UserUpdateSelf, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    out = UserPublic.model_validate(user).model_dump()
    out["status"] = user.status.value
    return UserPublic(**out)
