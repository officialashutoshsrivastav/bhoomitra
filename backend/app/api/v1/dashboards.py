from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_permissions, require_permissions
from app.core.permissions import P, Roles
from app.db.database import get_db
from app.models.datasets import Dataset, DatasetStatus, Observation
from app.models.gis import AdminUnit, GISFeature, GISLayer, RSProduct, RSScene, SpatialAnalysisRun
from app.models.identity import Organization, User, UserStatus
from app.models.intelligence import AIConversation, AIMessage, AnalyticsRun, Recommendation, Scenario, SimulationRun
from app.models.knowledge import Document, DocumentStatus, DocumentVersion, Policy, PolicyStatus, ProcessingStatus, ResearchProject, Visibility
from app.models.platform import Approval, AuditLog, BackgroundJob, Challenge, ChallengeStatus, Notification, Pilot, Submission, Task, Workspace
from app.schemas.common import DEMO_NOTICE

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _count(db: Session, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _demo_share(db: Session, model, flag_col) -> Dict[str, int]:
    total = int(db.scalar(select(func.count()).select_from(model)) or 0)
    demo = int(db.scalar(select(func.count()).select_from(model).where(flag_col.is_(True))) or 0)
    return {"total": total, "demo": demo, "real": total - demo}


def _series_by_month(db: Session, col, months: int = 12) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=30 * months)
    rows = db.execute(select(func.date_trunc("month", col).label("m"), func.count()).where(col >= since).group_by("m").order_by("m")).all()
    return [{"month": m.strftime("%Y-%m"), "count": c} for m, c in rows]


@router.get("/public-overview")
def public_overview(db: Session = Depends(get_db)):
    """Counts for the public landing page — computed live, with demo/synthetic
    shares reported so the UI can badge them. Never hard-coded."""
    docs = _demo_share(db, Document, Document.is_demo)
    datasets = _demo_share(db, Dataset, Dataset.is_demo)
    policies = _demo_share(db, Policy, Policy.is_demo)
    layers = _demo_share(db, GISLayer, GISLayer.is_demo)
    published_docs = _count(db, select(Document).where(Document.status == DocumentStatus.PUBLISHED, Document.visibility == Visibility.PUBLIC, Document.deleted_at.is_(None)))
    public_datasets = _count(db, select(Dataset).where(Dataset.status == DatasetStatus.PUBLISHED, Dataset.access_level.in_(["public", "open"]), Dataset.deleted_at.is_(None)))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notice": DEMO_NOTICE,
        "stats": [
            {"key": "documents", "label": "Research & policy documents", "value": published_docs, **docs},
            {"key": "datasets", "label": "Catalogued datasets", "value": public_datasets, **datasets},
            {"key": "policies", "label": "Policies tracked", "value": _count(db, select(Policy).where(Policy.deleted_at.is_(None))), **policies},
            {"key": "gis_layers", "label": "GIS layers", "value": _count(db, select(GISLayer).where(GISLayer.is_public.is_(True))), **layers},
            {"key": "admin_units", "label": "Administrative units mapped", "value": _count(db, select(AdminUnit)), "demo": _count(db, select(AdminUnit).where(AdminUnit.is_demo.is_(True)))},
            {"key": "organizations", "label": "Partner organisations", "value": _count(db, select(Organization).where(Organization.is_active.is_(True)))},
            {"key": "challenges", "label": "Innovation challenges", "value": _count(db, select(Challenge).where(Challenge.deleted_at.is_(None)))},
            {"key": "observations", "label": "Statistical observations", "value": int(db.scalar(select(func.count(Observation.id))) or 0)},
        ],
        "recent_documents": [{"id": str(d.id), "title": d.title, "document_type": d.document_type.value, "publication_date": d.publication_date.isoformat() if d.publication_date else None, "is_demo": d.is_demo} for d in db.scalars(select(Document).where(Document.status == DocumentStatus.PUBLISHED, Document.visibility == Visibility.PUBLIC, Document.deleted_at.is_(None)).order_by(Document.published_at.desc().nullslast()).limit(6)).all()],
        "open_challenges": [{"id": str(c.id), "title": c.title, "theme": c.theme, "closes_at": c.closes_at.isoformat() if c.closes_at else None, "is_demo": c.is_demo} for c in db.scalars(select(Challenge).where(Challenge.status == ChallengeStatus.OPEN, Challenge.deleted_at.is_(None)).limit(4)).all()],
        "policy_areas": [{"value": v, "count": c} for v, c in db.execute(select(Policy.policy_area, func.count()).where(Policy.deleted_at.is_(None)).group_by(Policy.policy_area).order_by(func.count().desc()).limit(8)).all()],
        "dataset_categories": [{"value": v.value, "count": c} for v, c in db.execute(select(Dataset.category, func.count()).where(Dataset.deleted_at.is_(None)).group_by(Dataset.category).order_by(func.count().desc()).limit(8)).all()],
    }


@router.get("/me")
def my_dashboard(user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    """Role-aware dashboard: returns the widgets the user is entitled to."""
    from app.api.deps import user_role_names

    roles = user_role_names(db, user)
    out: Dict[str, Any] = {"user": {"id": str(user.id), "name": user.full_name, "roles": roles}, "widgets": {}}
    out["widgets"]["my_activity"] = {
        "documents": _count(db, select(Document).where(Document.created_by == user.id, Document.deleted_at.is_(None))),
        "datasets": _count(db, select(Dataset).where(Dataset.owner_id == user.id, Dataset.deleted_at.is_(None))),
        "workspaces": _count(db, select(Workspace).where(Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))),
        "tasks_open": _count(db, select(Task).where(Task.assignee_id == user.id, Task.status.in_(["todo", "in_progress", "blocked"]))),
        "ai_questions": _count(db, select(AIMessage).join(AIConversation, AIConversation.id == AIMessage.conversation_id).where(AIMessage.role == "user", AIConversation.user_id == user.id)),
        "analytics_runs": _count(db, select(AnalyticsRun).where(AnalyticsRun.created_by == user.id)),
        "scenarios": _count(db, select(Scenario).where(Scenario.created_by == user.id)),
    }
    if P.DOCUMENT_REVIEW in perms or user.is_superuser:
        out["widgets"]["review_queue"] = {"documents_in_review": _count(db, select(Document).where(Document.status == DocumentStatus.IN_REVIEW)), "datasets_pending": _count(db, select(Dataset).where(Dataset.status == DatasetStatus.PENDING_APPROVAL)), "approvals_pending": _count(db, select(Approval).where(Approval.status == "pending"))}
    if P.DASHBOARD_NATIONAL in perms or user.is_superuser:
        out["widgets"]["national"] = national(db)
    if P.GIS_VIEW in perms or user.is_superuser:
        out["widgets"]["gis"] = {"layers": _count(db, select(GISLayer)), "features": int(db.scalar(select(func.count(GISFeature.id))) or 0), "spatial_runs": _count(db, select(SpatialAnalysisRun)), "rs_scenes": _count(db, select(RSScene)), "rs_products": _count(db, select(RSProduct))}
    if P.INNOVATION_EVALUATE in perms or P.INNOVATION_MANAGE in perms or user.is_superuser:
        out["widgets"]["innovation"] = {"open_challenges": _count(db, select(Challenge).where(Challenge.status == ChallengeStatus.OPEN)), "submissions_awaiting_evaluation": _count(db, select(Submission).where(Submission.status.in_(["submitted", "under_evaluation"]))), "pilots_active": _count(db, select(Pilot).where(Pilot.status == "active"))}
    if P.ADMIN_MANAGE_USERS in perms or user.is_superuser:
        out["widgets"]["admin"] = admin_overview(db)
    if Roles.RESEARCHER in roles or Roles.ACADEMIC in roles or Roles.RESEARCH_ORG in roles or user.is_superuser:
        out["widgets"]["research"] = {"my_projects": _count(db, select(ResearchProject).where(ResearchProject.lead_user_id == user.id, ResearchProject.deleted_at.is_(None))), "recent_publications": [{"id": str(d.id), "title": d.title, "document_type": d.document_type.value, "is_demo": d.is_demo} for d in db.scalars(select(Document).where(Document.status == DocumentStatus.PUBLISHED, Document.deleted_at.is_(None)).order_by(Document.published_at.desc().nullslast()).limit(5)).all()]}
    if Roles.POLICY_MAKER in roles or Roles.GOVERNMENT_OFFICIAL in roles or user.is_superuser:
        out["widgets"]["policy"] = {"active_policies": _count(db, select(Policy).where(Policy.status == PolicyStatus.ACTIVE, Policy.deleted_at.is_(None))), "scenarios_under_review": _count(db, select(Scenario).where(Scenario.status == "under_review")), "recent_recommendations": [{"id": str(r.id), "kind": r.kind, "title": r.title, "confidence": r.confidence, "is_demo": r.is_demo, "created_at": r.created_at.isoformat()} for r in db.scalars(select(Recommendation).order_by(Recommendation.created_at.desc()).limit(6)).all()]}
    out["notifications_unread"] = _count(db, select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return out


def national(db: Session) -> Dict[str, Any]:
    states = [{"id": str(u.id), "name": u.name, "area_km2": u.area_km2, "is_demo": u.is_demo, "districts": _count(db, select(AdminUnit).where(AdminUnit.parent_id == u.id))} for u in db.scalars(select(AdminUnit).where(AdminUnit.level == "STATE").order_by(AdminUnit.name).limit(40)).all()]
    return {
        "states": states,
        "documents_by_type": [{"value": v.value, "count": c} for v, c in db.execute(select(Document.document_type, func.count()).where(Document.deleted_at.is_(None)).group_by(Document.document_type).order_by(func.count().desc())).all()],
        "documents_by_month": _series_by_month(db, Document.created_at),
        "datasets_by_status": [{"value": v.value, "count": c} for v, c in db.execute(select(Dataset.status, func.count()).where(Dataset.deleted_at.is_(None)).group_by(Dataset.status)).all()],
        "policies_by_area": [{"value": v, "count": c} for v, c in db.execute(select(Policy.policy_area, func.count()).where(Policy.deleted_at.is_(None)).group_by(Policy.policy_area).order_by(func.count().desc()).limit(10)).all()],
        "layer_coverage": [{"id": str(l.id), "name": l.name, "category": l.category.value, "features": l.feature_count, "is_demo": l.is_demo} for l in db.scalars(select(GISLayer).order_by(GISLayer.feature_count.desc()).limit(10)).all()],
        "simulations": {"scenarios": _count(db, select(Scenario)), "runs": _count(db, select(SimulationRun)), "approved": _count(db, select(Scenario).where(Scenario.status == "approved"))},
        "ai": {"questions": _count(db, select(AIMessage).where(AIMessage.role == "user")), "answers_with_sufficient_evidence": _count(db, select(AIMessage).where(AIMessage.role == "assistant", AIMessage.evidence_sufficient.is_(True)))},
        "notice": DEMO_NOTICE,
    }


@router.get("/national")
def national_dashboard(user: User = Depends(require_permissions(P.DASHBOARD_NATIONAL)), db: Session = Depends(get_db)):
    return national(db)


def admin_overview(db: Session) -> Dict[str, Any]:
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    return {
        "users": {"total": _count(db, select(User)), "active": _count(db, select(User).where(User.status == UserStatus.ACTIVE)), "pending": _count(db, select(User).where(User.status == UserStatus.PENDING)), "disabled": _count(db, select(User).where(User.status == UserStatus.DISABLED))},
        "organizations": _count(db, select(Organization).where(Organization.deleted_at.is_(None))),
        "approvals_pending": _count(db, select(Approval).where(Approval.status == "pending")),
        "processing": {"versions_failed": _count(db, select(DocumentVersion).where(DocumentVersion.processing_status == ProcessingStatus.FAILED)), "versions_in_progress": _count(db, select(DocumentVersion).where(DocumentVersion.processing_status.in_([ProcessingStatus.UPLOADED, ProcessingStatus.VALIDATING, ProcessingStatus.PROCESSING, ProcessingStatus.OCR_RUNNING, ProcessingStatus.INDEXING]))), "jobs_failed": _count(db, select(BackgroundJob).where(BackgroundJob.status == "failed")), "jobs_queued": _count(db, select(BackgroundJob).where(BackgroundJob.status.in_(["queued", "running"])))},
        "audit_events_24h": _count(db, select(AuditLog).where(AuditLog.created_at >= day_ago)),
        "failed_logins_24h": _count(db, select(AuditLog).where(AuditLog.action == "auth.login", AuditLog.result == "failure", AuditLog.created_at >= day_ago)),
        "signups_by_month": _series_by_month(db, User.created_at, 6),
    }


@router.get("/admin")
def admin_dashboard(user: User = Depends(require_permissions(P.ADMIN_MANAGE_USERS, P.ADMIN_MANAGE_CONFIG, any_of=True)), db: Session = Depends(get_db)):
    return admin_overview(db)
