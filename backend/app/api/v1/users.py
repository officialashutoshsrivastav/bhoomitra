from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_permissions, require_permissions, user_role_names
from app.audit import service as audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import Department, Organization, OrganizationMember, User, UserStatus
from app.schemas.common import Message, Page, PageParams
from app.services.document_service import unique_slug

router = APIRouter(prefix="/users", tags=["users"])


def _user_dict(db: Session, u: User, org_names: dict) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "designation": u.designation, "status": u.status.value, "organization_id": str(u.primary_organization_id) if u.primary_organization_id else None, "organization_name": org_names.get(u.primary_organization_id), "roles": user_role_names(db, u), "is_superuser": u.is_superuser, "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None, "created_at": u.created_at.isoformat()}


@router.get("")
def list_users(page: PageParams = Depends(), q: Annotated[Optional[str], Query(max_length=120)] = None, organization_id: Optional[uuid.UUID] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Directory of active users (name, designation, organisation) for collaboration features."""
    stmt = select(User).where(User.status == UserStatus.ACTIVE)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if organization_id:
        stmt = stmt.where(User.primary_organization_id == organization_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.full_name).offset(page.offset).limit(page.page_size)).all()
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    return Page.build([{"id": str(u.id), "full_name": u.full_name, "email": u.email, "designation": u.designation, "organization_name": org_names.get(u.primary_organization_id)} for u in rows], total, page.page, page.page_size)


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise NotFoundError("User not found")
    org_names = {o.id: o.name for o in db.scalars(select(Organization)).all()}
    out = _user_dict(db, u, org_names)
    if not (user.is_superuser or P.ADMIN_MANAGE_USERS in perms or u.id == user.id):
        out = {k: out[k] for k in ("id", "full_name", "designation", "organization_name", "roles")}
    return out


# ---------------------------------------------------------------------------
# Organisations
# ---------------------------------------------------------------------------
org_router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    org_type: str = Field("government", pattern="^(government|ministry|state_department|research_institute|university|ngo|industry|international|other)$")
    description: Optional[str] = None
    website: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=100)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    org_type: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    state: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None


def _org_dict(db: Session, o: Organization) -> dict:
    return {"id": str(o.id), "name": o.name, "slug": o.slug, "org_type": o.org_type, "description": o.description, "website": o.website, "state": o.state, "is_active": o.is_active, "member_count": db.scalar(select(func.count(User.id)).where(User.primary_organization_id == o.id)) or 0, "departments": [{"id": str(d.id), "name": d.name, "code": d.code} for d in o.departments], "created_at": o.created_at.isoformat()}


@org_router.get("")
def list_organizations(page: PageParams = Depends(), q: Optional[str] = None, org_type: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(Organization).where(Organization.deleted_at.is_(None), Organization.is_active.is_(True))
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    if org_type:
        stmt = stmt.where(Organization.org_type == org_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Organization.name).offset(page.offset).limit(page.page_size)).all()
    return Page.build([_org_dict(db, o) for o in rows], total, page.page, page.page_size)


@org_router.post("", status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_ORGS)), db: Session = Depends(get_db)):
    if db.scalar(select(Organization.id).where(Organization.name == payload.name)):
        raise ConflictError("Organization already exists")
    o = Organization(**payload.model_dump(), slug=unique_slug(db, Organization, payload.name))
    db.add(o)
    db.flush()
    audit.record(db, "organization.create", user=user, resource_type="organization", resource_id=o.id, request=request)
    db.commit()
    return _org_dict(db, o)


@org_router.get("/{org_id}")
def get_organization(org_id: uuid.UUID, db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o or o.deleted_at:
        raise NotFoundError("Organization not found")
    return _org_dict(db, o)


@org_router.patch("/{org_id}")
def update_organization(org_id: uuid.UUID, payload: OrganizationUpdate, request: Request, user: User = Depends(require_permissions(P.ADMIN_MANAGE_ORGS)), db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o or o.deleted_at:
        raise NotFoundError("Organization not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(o, k, v)
    audit.record(db, "organization.update", user=user, resource_type="organization", resource_id=o.id, detail={"fields": list(changes)}, request=request)
    db.commit()
    return _org_dict(db, o)


@org_router.post("/{org_id}/departments", status_code=status.HTTP_201_CREATED)
def add_department(org_id: uuid.UUID, payload: DepartmentIn, user: User = Depends(require_permissions(P.ADMIN_MANAGE_ORGS)), db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o:
        raise NotFoundError("Organization not found")
    if any(d.name == payload.name for d in o.departments):
        raise ConflictError("Department already exists")
    d = Department(organization_id=o.id, **payload.model_dump())
    db.add(d)
    db.commit()
    return {"id": str(d.id), "name": d.name, "code": d.code}


@org_router.get("/{org_id}/members")
def org_members(org_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.primary_organization_id == org_id, User.status == UserStatus.ACTIVE).order_by(User.full_name).limit(500)).all()
    return {"items": [{"id": str(u.id), "full_name": u.full_name, "designation": u.designation, "roles": user_role_names(db, u)} for u in rows]}
