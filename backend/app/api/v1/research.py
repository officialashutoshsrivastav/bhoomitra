from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_current_user_optional, get_permissions, require_permissions
from app.audit import service as audit
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.knowledge import Policy, PolicyIndicator, PolicyStatus, ResearchOutput, ResearchProject, ResearchStatus
from app.schemas.common import Message, Page, PageParams
from app.schemas.knowledge import PolicyCreate, PolicyDetail, PolicyIndicatorCreate, PolicyIndicatorOut, PolicyOut, PolicyUpdate, ResearchOutputCreate, ResearchOutputOut, ResearchProjectCreate, ResearchProjectOut, ResearchProjectUpdate
from app.search import indexer
from app.services.document_service import unique_slug

research_router = APIRouter(prefix="/research", tags=["research"])
policy_router = APIRouter(prefix="/policies", tags=["policies"])


# ---------------------------------------------------------------------------
# Research projects
# ---------------------------------------------------------------------------
def _get_project(db: Session, pid: uuid.UUID) -> ResearchProject:
    p = db.scalar(select(ResearchProject).options(selectinload(ResearchProject.outputs)).execution_options(populate_existing=True).where(ResearchProject.id == pid, ResearchProject.deleted_at.is_(None)))
    if not p:
        raise NotFoundError("Research project not found")
    return p


def _can_manage(p: ResearchProject, user: User, perms: set) -> bool:
    return user.is_superuser or p.lead_user_id == user.id or P.RESEARCH_MANAGE in perms and (p.organization_id is None or p.organization_id == user.primary_organization_id) or P.RESEARCH_PUBLISH in perms


@research_router.get("", response_model=Page[ResearchProjectOut])
def list_projects(page: PageParams = Depends(), q: Annotated[Optional[str], Query(max_length=200)] = None, research_area: Optional[str] = None, status_filter: Annotated[Optional[ResearchStatus], Query(alias="status")] = None, mine: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(ResearchProject).options(selectinload(ResearchProject.outputs)).where(ResearchProject.deleted_at.is_(None))
    if q:
        stmt = stmt.where(or_(ResearchProject.title.ilike(f"%{q}%"), ResearchProject.summary.ilike(f"%{q}%")))
    if research_area:
        stmt = stmt.where(ResearchProject.research_area.ilike(f"%{research_area}%"))
    if status_filter:
        stmt = stmt.where(ResearchProject.status == status_filter)
    if mine:
        stmt = stmt.where(ResearchProject.lead_user_id == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ResearchProject.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([ResearchProjectOut.model_validate(r) for r in rows], total, page.page, page.page_size)


@research_router.post("", response_model=ResearchProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ResearchProjectCreate, request: Request, user: User = Depends(require_permissions(P.RESEARCH_CREATE)), db: Session = Depends(get_db)):
    p = ResearchProject(**payload.model_dump(), lead_user_id=user.id)
    db.add(p)
    db.flush()
    audit.record(db, "research.create", user=user, resource_type="research_project", resource_id=p.id, request=request)
    db.commit()
    indexer.index_research(db, p)
    return ResearchProjectOut.model_validate(_get_project(db, p.id))


@research_router.get("/{pid}", response_model=ResearchProjectOut)
def get_project(pid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ResearchProjectOut.model_validate(_get_project(db, pid))


@research_router.patch("/{pid}", response_model=ResearchProjectOut)
def update_project(pid: uuid.UUID, payload: ResearchProjectUpdate, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    if not _can_manage(p, user, perms):
        raise ForbiddenError("You cannot manage this project")
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] == ResearchStatus.PUBLISHED and P.RESEARCH_PUBLISH not in perms and not user.is_superuser:
        raise ForbiddenError("research.publish permission required to publish")
    for k, v in changes.items():
        setattr(p, k, v)
    audit.record(db, "research.update", user=user, resource_type="research_project", resource_id=p.id, detail={"fields": list(changes)}, request=request)
    db.commit()
    indexer.index_research(db, p)
    return ResearchProjectOut.model_validate(_get_project(db, pid))


@research_router.post("/{pid}/outputs", response_model=ResearchOutputOut, status_code=status.HTTP_201_CREATED)
def add_output(pid: uuid.UUID, payload: ResearchOutputCreate, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    p = _get_project(db, pid)
    if not _can_manage(p, user, perms):
        raise ForbiddenError("You cannot manage this project")
    o = ResearchOutput(project_id=p.id, **payload.model_dump())
    db.add(o)
    audit.record(db, "research.add_output", user=user, resource_type="research_project", resource_id=p.id, request=request)
    db.commit()
    db.refresh(o)
    return ResearchOutputOut.model_validate(o)


@research_router.delete("/{pid}", response_model=Message)
def delete_project(pid: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.RESEARCH_MANAGE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    p = _get_project(db, pid)
    if not _can_manage(p, user, perms):
        raise ForbiddenError("You cannot manage this project")
    p.deleted_at = datetime.now(timezone.utc)
    audit.record(db, "research.delete", user=user, resource_type="research_project", resource_id=p.id, request=request)
    db.commit()
    indexer.remove("research_project", p.id)
    return Message(message="Project archived")


# ---------------------------------------------------------------------------
# Policies + indicators
# ---------------------------------------------------------------------------
def _get_policy(db: Session, pid: uuid.UUID) -> Policy:
    p = db.scalar(select(Policy).options(selectinload(Policy.indicators)).execution_options(populate_existing=True).where(Policy.id == pid, Policy.deleted_at.is_(None)))
    if not p:
        raise NotFoundError("Policy not found")
    return p


@policy_router.get("", response_model=Page[PolicyOut])
def list_policies(page: PageParams = Depends(), q: Annotated[Optional[str], Query(max_length=200)] = None, policy_area: Optional[str] = None, level: Optional[str] = None, status_filter: Annotated[Optional[PolicyStatus], Query(alias="status")] = None, year: Optional[int] = None, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    stmt = select(Policy).where(Policy.deleted_at.is_(None))
    if user is None:
        stmt = stmt.where(Policy.status.in_([PolicyStatus.ACTIVE, PolicyStatus.SUPERSEDED]))
    if q:
        stmt = stmt.where(or_(Policy.title.ilike(f"%{q}%"), Policy.summary.ilike(f"%{q}%")))
    if policy_area:
        stmt = stmt.where(Policy.policy_area.ilike(f"%{policy_area}%"))
    if level:
        stmt = stmt.where(Policy.level == level)
    if status_filter:
        stmt = stmt.where(Policy.status == status_filter)
    if year:
        stmt = stmt.where(func.extract("year", Policy.effective_date) == year)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Policy.effective_date.desc().nullslast()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([PolicyOut.model_validate(r) for r in rows], total, page.page, page.page_size)


@policy_router.get("/facets")
def policy_facets(db: Session = Depends(get_db)):
    base = select(Policy).where(Policy.deleted_at.is_(None)).subquery()
    out = {}
    for name, col in (("policy_area", base.c.policy_area), ("level", base.c.level), ("status", base.c.status), ("ministry", base.c.ministry)):
        out[name] = [{"value": v, "count": c} for v, c in db.execute(select(col, func.count()).where(col.is_not(None)).group_by(col).order_by(func.count().desc())).all()]
    years = db.execute(select(func.extract("year", base.c.effective_date).label("y"), func.count()).where(base.c.effective_date.is_not(None)).group_by("y").order_by(func.desc("y"))).all()
    out["year"] = [{"value": str(int(y)), "count": c} for y, c in years]
    return out


@policy_router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def create_policy(payload: PolicyCreate, request: Request, user: User = Depends(require_permissions(P.POLICY_MANAGE)), db: Session = Depends(get_db)):
    p = Policy(**payload.model_dump(), slug=unique_slug(db, Policy, payload.title), created_by=user.id)
    db.add(p)
    db.flush()
    audit.record(db, "policy.create", user=user, resource_type="policy", resource_id=p.id, request=request)
    db.commit()
    indexer.index_policy(db, p)
    return PolicyOut.model_validate(p)


@policy_router.get("/{pid}", response_model=PolicyDetail)
def get_policy(pid: uuid.UUID, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    p = _get_policy(db, pid)
    if user is None and p.status not in (PolicyStatus.ACTIVE, PolicyStatus.SUPERSEDED):
        raise NotFoundError("Policy not found")
    return PolicyDetail.model_validate(p)


@policy_router.patch("/{pid}", response_model=PolicyOut)
def update_policy(pid: uuid.UUID, payload: PolicyUpdate, request: Request, user: User = Depends(require_permissions(P.POLICY_MANAGE)), db: Session = Depends(get_db)):
    p = _get_policy(db, pid)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit.record(db, "policy.update", user=user, resource_type="policy", resource_id=p.id, detail={"fields": list(changes)}, request=request)
    db.commit()
    indexer.index_policy(db, p)
    return PolicyOut.model_validate(p)


@policy_router.post("/{pid}/indicators", response_model=PolicyIndicatorOut, status_code=status.HTTP_201_CREATED)
def add_indicator(pid: uuid.UUID, payload: PolicyIndicatorCreate, request: Request, user: User = Depends(require_permissions(P.POLICY_MANAGE)), db: Session = Depends(get_db)):
    p = _get_policy(db, pid)
    ind = PolicyIndicator(policy_id=p.id, **payload.model_dump())
    db.add(ind)
    audit.record(db, "policy.add_indicator", user=user, resource_type="policy", resource_id=p.id, detail={"code": payload.code, "value_kind": payload.value_kind}, request=request)
    db.commit()
    db.refresh(ind)
    return PolicyIndicatorOut.model_validate(ind)


@policy_router.get("/indicators/series", response_model=List[PolicyIndicatorOut])
def indicator_series(code: Annotated[str, Query(max_length=80)], admin_unit_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db)):
    stmt = select(PolicyIndicator).where(PolicyIndicator.code == code)
    if admin_unit_id:
        stmt = stmt.where(PolicyIndicator.admin_unit_id == admin_unit_id)
    rows = db.scalars(stmt.order_by(PolicyIndicator.period_start.asc().nullsfirst()).limit(500)).all()
    return [PolicyIndicatorOut.model_validate(r) for r in rows]
