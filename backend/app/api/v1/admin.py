from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_permissions, require_permissions, require_superuser, user_role_names
from app.audit import service as audit
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import ALL_PERMISSIONS, PERMISSION_DESCRIPTIONS, ROLE_LABELS, ROLE_PERMISSIONS, P, Roles
from app.core.security import hash_password, validate_password_strength
from app.db.database import get_db
from app.models.datasets import Dataset, DatasetStatus
from app.models.identity import Organization, Permission, RefreshToken, Role, RolePermission, SystemSetting, User, UserRole, UserStatus
from app.models.intelligence import Scenario, ScenarioStatus
from app.models.knowledge import Document, DocumentStatus
from app.models.platform import Approval, BackgroundJob, Workspace
from app.notifications.service import notify
from app.schemas.common import Message, Page, PageParams
from app.services import auth_service
from app.workers.dispatch import enqueue, worker_status

router = APIRouter(prefix="/admin", tags=["admin"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=10, max_length=128)
    designation: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[uuid.UUID] = None
    roles: List[str] = Field(default_factory=lambda: [Roles.PUBLIC])
    status: UserStatus = UserStatus.ACTIVE


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    designation: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    status: Optional[UserStatus] = None


class RolesIn(BaseModel):
    roles: List[str] = Field(min_length=1)


def _user_dict(db: Session, u: User, org_names: Dict[uuid.UUID, str]) -> Dict[str, Any]:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "designation": u.designation, "phone": u.phone, "status": u.status.value, "is_superuser": u.is_superuser, "organization_id": str(u.primary_organization_id) if u.primary_organization_id else None, "organization_name": org_names.get(u.primary_organization_id), "department_id": str(u.department_id) if u.department_id else None, "roles": user_role_names(db, u), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None, "failed_login_attempts": u.failed_login_attempts, "locked_until": u.locked_until.isoformat() if u.locked_until else None, "created_at": u.created_at.isoformat()}


@router.get("/users")
def list_users(page: PageParams = Depends(), q: Optional[str] = None, status_filter: Annotated[Optional[UserStatus], Query(alias="status")] = None, role: Optional[str] = None, organization_id: Optional[uuid.UUID] = None, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS)), db: Session = Depends(get_db)):
    stmt = select(User)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if status_filter:
        stmt = stmt.where(User.status == status_filter)
    if organization_id:
        stmt = stmt.where(User.primary_organization_id == organization_id)
    if role:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == role)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    return Page.build([_user_dict(db, u, org_names) for u in rows], total, page.page, page.page_size)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: AdminUserCreate, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS)), db: Session = Depends(get_db)):
    problem = validate_password_strength(payload.password)
    if problem:
        raise ValidationFailed(problem)
    if db.scalar(select(User.id).where(User.email == payload.email.lower())):
        raise ConflictError("Email already registered")
    for r in payload.roles:
        if r not in ROLE_PERMISSIONS:
            raise ValidationFailed(f"Unknown role {r}")
        if r in (Roles.SUPER_ADMIN, Roles.PLATFORM_ADMIN) and not user.is_superuser:
            raise ForbiddenError("Only super administrators can grant administrator roles")
    u = User(email=payload.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.password), designation=payload.designation, primary_organization_id=payload.organization_id, status=payload.status, password_changed_at=_now())
    db.add(u)
    db.flush()
    for r in payload.roles:
        auth_service.assign_role(db, u, r, granted_by=user)
    audit.record(db, "admin.user_create", user=user, resource_type="user", resource_id=u.id, detail={"roles": payload.roles, "status": payload.status.value}, request=request)
    db.commit()
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    return _user_dict(db, u, org_names)


def _get_user(db: Session, uid: uuid.UUID) -> User:
    u = db.get(User, uid)
    if not u:
        raise NotFoundError("User not found")
    return u


@router.get("/users/{uid}")
def get_user(uid: uuid.UUID, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS)), db: Session = Depends(get_db)):
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    return _user_dict(db, _get_user(db, uid), org_names)


@router.patch("/users/{uid}")
def update_user(uid: uuid.UUID, payload: AdminUserUpdate, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS)), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    if u.is_superuser and not user.is_superuser:
        raise ForbiddenError("Cannot modify a super administrator")
    changes = payload.model_dump(exclude_unset=True)
    if "organization_id" in changes:
        u.primary_organization_id = changes.pop("organization_id")
    for k, v in changes.items():
        setattr(u, k, v)
    if changes.get("status") == UserStatus.ACTIVE:
        u.failed_login_attempts = 0
        u.locked_until = None
        u.activation_token_hash = None
    if changes.get("status") == UserStatus.DISABLED:
        for t in u.refresh_tokens:
            t.revoked_at = _now()
    audit.record(db, "admin.user_update", user=user, resource_type="user", resource_id=u.id, detail={k: (v.value if hasattr(v, "value") else str(v)) for k, v in changes.items()}, request=request)
    db.commit()
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    return _user_dict(db, u, org_names)


@router.post("/users/{uid}/activate")
def activate_user(uid: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS, P.ADMIN_APPROVALS, any_of=True)), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    u.status = UserStatus.ACTIVE
    u.activation_token_hash = None
    u.failed_login_attempts = 0
    u.locked_until = None
    notify(db, u.id, "account", "Account activated", "Your Bhoomitra account has been activated by an administrator.", link="/login", email=True)
    audit.record(db, "admin.user_activate", user=user, resource_type="user", resource_id=u.id, request=request)
    db.commit()
    return Message(message="User activated")


@router.post("/users/{uid}/disable")
def disable_user(uid: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS)), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    if u.id == user.id:
        raise ConflictError("You cannot disable your own account")
    if u.is_superuser and not user.is_superuser:
        raise ForbiddenError("Cannot disable a super administrator")
    u.status = UserStatus.DISABLED
    for t in u.refresh_tokens:
        t.revoked_at = _now()
    audit.record(db, "admin.user_disable", user=user, resource_type="user", resource_id=u.id, request=request)
    db.commit()
    return Message(message="User disabled and sessions revoked")


@router.put("/users/{uid}/roles")
def set_roles(uid: uuid.UUID, payload: RolesIn, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_ROLES)), db: Session = Depends(get_db)):
    u = _get_user(db, uid)
    for r in payload.roles:
        if r not in ROLE_PERMISSIONS:
            raise ValidationFailed(f"Unknown role {r}")
        if r in (Roles.SUPER_ADMIN, Roles.PLATFORM_ADMIN) and not user.is_superuser:
            raise ForbiddenError("Only super administrators can grant administrator roles")
    if u.id == user.id and Roles.SUPER_ADMIN not in payload.roles and user.is_superuser and not any(r == Roles.SUPER_ADMIN for r in payload.roles):
        raise ConflictError("You cannot remove your own super administrator role")
    for ur in list(u.roles):
        db.delete(ur)
    db.flush()
    for r in payload.roles:
        auth_service.assign_role(db, u, r, granted_by=user)
    u.is_superuser = Roles.SUPER_ADMIN in payload.roles
    audit.record(db, "admin.user_roles", user=user, resource_type="user", resource_id=u.id, detail={"roles": payload.roles}, request=request)
    db.commit()
    return {"user_id": str(u.id), "roles": user_role_names(db, u)}


@router.post("/users/{uid}/reset-password")
def admin_reset_password(uid: uuid.UUID, request: Request, new_password: Annotated[str, Query(min_length=10, max_length=128)], user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    problem = validate_password_strength(new_password)
    if problem:
        raise ValidationFailed(problem)
    u = _get_user(db, uid)
    u.password_hash = hash_password(new_password)
    u.password_changed_at = _now()
    for t in u.refresh_tokens:
        t.revoked_at = _now()
    audit.record(db, "admin.user_password_reset", user=user, resource_type="user", resource_id=u.id, request=request)
    db.commit()
    return Message(message="Password reset; all sessions revoked")


# ---------------------------------------------------------------------------
# Roles & permissions (read-only matrix + descriptions)
# ---------------------------------------------------------------------------
@router.get("/roles")
def roles(user: User = Depends(require_permissions(P.ADMIN_MANAGE_ROLES, P.ADMIN_MANAGE_USERS, any_of=True)), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Role.name, func.count(UserRole.user_id)).outerjoin(UserRole, UserRole.role_id == Role.id).group_by(Role.name)).all())
    return {"roles": [{"name": r, "label": ROLE_LABELS[r], "permissions": sorted(ROLE_PERMISSIONS[r]), "user_count": int(counts.get(r, 0))} for r in ROLE_PERMISSIONS], "permissions": [{"code": p, "description": PERMISSION_DESCRIPTIONS.get(p, "")} for p in sorted(ALL_PERMISSIONS)]}


# ---------------------------------------------------------------------------
# Approvals queue
# ---------------------------------------------------------------------------
class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: Optional[str] = Field(None, max_length=4000)


def _approval_dict(a: Approval, users: Dict[uuid.UUID, User]) -> Dict[str, Any]:
    return {"id": str(a.id), "target_type": a.target_type, "target_id": str(a.target_id), "title": a.title, "status": a.status, "requested_by": str(a.requested_by), "requested_by_name": users[a.requested_by].full_name if a.requested_by in users else None, "decided_by": str(a.decided_by) if a.decided_by else None, "decided_at": a.decided_at.isoformat() if a.decided_at else None, "decision_note": a.decision_note, "created_at": a.created_at.isoformat(), "link": {"document": f"/app/repository/{a.target_id}", "dataset": f"/app/datasets/{a.target_id}", "workspace": f"/app/workspaces/{a.target_id}", "user": f"/app/admin/users/{a.target_id}"}.get(a.target_type)}


@router.get("/approvals")
def approvals(page: PageParams = Depends(), status_filter: Annotated[str, Query(alias="status")] = "pending", target_type: Optional[str] = None, user: User = Depends(require_permissions(P.ADMIN_APPROVALS, P.DOCUMENT_REVIEW, P.DATASET_APPROVE, any_of=True)), db: Session = Depends(get_db)):
    stmt = select(Approval)
    if status_filter != "all":
        stmt = stmt.where(Approval.status == status_filter)
    if target_type:
        stmt = stmt.where(Approval.target_type == target_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Approval.created_at.asc()).offset(page.offset).limit(page.page_size)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.requested_by for a in rows}))).all()} if rows else {}
    pending_users = db.scalars(select(User).where(User.status == UserStatus.PENDING).order_by(User.created_at.asc()).limit(50)).all()
    return {**Page.build([_approval_dict(a, users) for a in rows], total, page.page, page.page_size).model_dump(), "pending_user_activations": [{"id": str(u.id), "email": u.email, "full_name": u.full_name, "created_at": u.created_at.isoformat()} for u in pending_users]}


@router.post("/approvals/{aid}/decide")
def decide_approval(aid: uuid.UUID, payload: ApprovalDecision, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    a = db.get(Approval, aid)
    if not a:
        raise NotFoundError("Approval not found")
    if a.status != "pending":
        raise ConflictError("Approval already decided")
    if a.target_type == "document":
        if P.DOCUMENT_REVIEW not in perms and not user.is_superuser:
            raise ForbiddenError("document.review permission required")
        from app.services import document_service

        doc = db.get(Document, a.target_id)
        if doc and doc.status == DocumentStatus.IN_REVIEW:
            document_service.review(db, doc, "approve" if payload.decision == "approve" else "reject", payload.note, user, request)
    elif a.target_type == "dataset":
        if P.DATASET_APPROVE not in perms and not user.is_superuser:
            raise ForbiddenError("dataset.approve permission required")
        from app.services import dataset_service

        ds = db.get(Dataset, a.target_id)
        if ds and ds.status == DatasetStatus.PENDING_APPROVAL:
            dataset_service.approve(db, ds, user, payload.decision, payload.note, request)
    elif a.target_type == "workspace":
        if P.WORKSPACE_MANAGE not in perms and not user.is_superuser:
            raise ForbiddenError("workspace.manage permission required")
    elif P.ADMIN_APPROVALS not in perms and not user.is_superuser:
        raise ForbiddenError("admin.manage_approvals permission required")
    a = db.get(Approval, aid)
    if a.status == "pending":
        a.status = "approved" if payload.decision == "approve" else "rejected"
        a.decided_by = user.id
        a.decided_at = _now()
        a.decision_note = payload.note
    audit.record(db, f"admin.approval_{payload.decision}", user=user, resource_type=a.target_type, resource_id=a.target_id, detail={"approval": str(a.id), "note": payload.note}, request=request)
    db.commit()
    return _approval_dict(a, {user.id: user})


# ---------------------------------------------------------------------------
# System settings
# ---------------------------------------------------------------------------
class SettingIn(BaseModel):
    key: str = Field(min_length=2, max_length=120, pattern="^[a-z0-9_.]+$")
    value: str = Field(max_length=4000)
    value_type: str = Field("string", pattern="^(string|int|float|bool|json)$")
    description: Optional[str] = Field(None, max_length=255)
    is_secret: bool = False


@router.get("/settings")
def list_settings(user: User = Depends(require_permissions(P.ADMIN_MANAGE_CONFIG)), db: Session = Depends(get_db)):
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return {"items": [{"key": s.key, "value": "••••••" if s.is_secret else s.value, "value_type": s.value_type, "description": s.description, "is_secret": s.is_secret, "updated_at": s.updated_at.isoformat()} for s in rows], "runtime": {"app_env": settings.app_env, "ai_provider": settings.ai_provider, "embedding_provider": settings.embedding_provider, "embedding_dim": settings.embedding_dim, "storage_backend": settings.storage_backend, "task_execution_mode": settings.task_execution_mode, "opensearch": bool(settings.opensearch_url), "email_backend": settings.email_backend, "max_upload_mb": settings.max_upload_mb, "demo_data_enabled": settings.demo_data_enabled}}


@router.put("/settings")
def upsert_setting(payload: SettingIn, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_CONFIG)), db: Session = Depends(get_db)):
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == payload.key))
    if s:
        s.value, s.value_type, s.description, s.is_secret, s.updated_by = payload.value, payload.value_type, payload.description, payload.is_secret, user.id
    else:
        s = SystemSetting(**payload.model_dump(), updated_by=user.id)
        db.add(s)
    audit.record(db, "admin.setting_upsert", user=user, resource_type="system_setting", detail={"key": payload.key}, request=request)
    db.commit()
    return {"key": s.key, "value": "••••••" if s.is_secret else s.value, "value_type": s.value_type}


# ---------------------------------------------------------------------------
# Jobs, workers, maintenance
# ---------------------------------------------------------------------------
@router.get("/jobs")
def jobs(page: PageParams = Depends(), status_filter: Annotated[Optional[str], Query(alias="status")] = None, job_type: Optional[str] = None, user: User = Depends(require_permissions(P.ADMIN_MANAGE_CONFIG)), db: Session = Depends(get_db)):
    stmt = select(BackgroundJob)
    if status_filter:
        stmt = stmt.where(BackgroundJob.status == status_filter)
    if job_type:
        stmt = stmt.where(BackgroundJob.job_type == job_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(BackgroundJob.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    items = [{"id": str(j.id), "job_type": j.job_type, "status": j.status, "progress": j.progress, "target_type": j.target_type, "target_id": str(j.target_id) if j.target_id else None, "retry_count": j.retry_count, "max_retries": j.max_retries, "error": j.error, "result": j.result, "created_at": j.created_at.isoformat(), "started_at": j.started_at.isoformat() if j.started_at else None, "completed_at": j.completed_at.isoformat() if j.completed_at else None} for j in rows]
    return {**Page.build(items, total, page.page, page.page_size).model_dump(), "workers": worker_status()}


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: uuid.UUID, user: User = Depends(require_permissions(P.ADMIN_MANAGE_CONFIG)), db: Session = Depends(get_db)):
    j = db.get(BackgroundJob, job_id)
    if not j:
        raise NotFoundError("Job not found")
    if j.status not in ("failed", "cancelled"):
        raise ConflictError("Only failed or cancelled jobs can be retried")
    new = enqueue(db, j.job_type, target_type=j.target_type, target_id=j.target_id, payload=j.payload or {}, created_by=user.id, max_retries=j.max_retries)
    return {"job_id": str(new.id), "status": new.status}


@router.post("/maintenance/reindex")
def reindex(user: User = Depends(require_permissions(P.ADMIN_MANAGE_CONFIG)), db: Session = Depends(get_db)):
    job = enqueue(db, "search.reindex", target_type="search", target_id=None, payload={}, created_by=user.id)
    return {"job_id": str(job.id), "status": job.status}


@router.get("/overview")
def overview(user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS, P.ADMIN_MANAGE_CONFIG, any_of=True)), db: Session = Depends(get_db)):
    from app.api.v1.dashboards import admin_overview

    return {**admin_overview(db), "workers": worker_status(), "scenarios_under_review": db.scalar(select(func.count(Scenario.id)).where(Scenario.status == ScenarioStatus.UNDER_REVIEW)) or 0, "workspaces": db.scalar(select(func.count(Workspace.id)).where(Workspace.deleted_at.is_(None))) or 0}


# ---------------------------------------------------------------------------
# Audit (read-only)
# ---------------------------------------------------------------------------
@audit_router.get("")
def audit_search(page: PageParams = Depends(), action: Optional[str] = None, user_id: Optional[uuid.UUID] = None, resource_type: Optional[str] = None, resource_id: Optional[str] = None, result: Annotated[Optional[str], Query(pattern="^(success|failure|denied)$")] = None, user: User = Depends(require_permissions(P.AUDIT_READ)), db: Session = Depends(get_db)):
    rows, total = audit.search(db, action=action, user_id=user_id, resource_type=resource_type, resource_id=resource_id, result=result, offset=page.offset, limit=page.page_size)
    items = [{"id": str(a.id), "action": a.action, "result": a.result, "user_id": str(a.user_id) if a.user_id else None, "user_email": a.user_email, "resource_type": a.resource_type, "resource_id": a.resource_id, "detail": a.detail, "ip_address": a.ip_address, "request_id": a.request_id, "created_at": a.created_at.isoformat()} for a in rows]
    return Page.build(items, total, page.page, page.page_size)


@audit_router.get("/actions")
def audit_actions(user: User = Depends(require_permissions(P.AUDIT_READ)), db: Session = Depends(get_db)):
    from app.models.platform import AuditLog

    rows = db.execute(select(AuditLog.action, func.count()).group_by(AuditLog.action).order_by(func.count().desc()).limit(100)).all()
    return {"items": [{"action": a, "count": c} for a, c in rows]}
