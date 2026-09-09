from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_permissions, require_permissions
from app.audit import service as audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.platform import Report
from app.reporting import service as reporting
from app.schemas.common import Page, PageParams
from app.storage.service import get_storage

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRequest(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    report_type: str = Field(pattern="^(repository_summary|dataset_export|policy_indicators|simulation_run|analytics_run|innovation_summary|gis_layer_summary|evidence_trace)$")
    format: str = Field("pdf", pattern="^(csv|xlsx|pdf)$")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    methodology: Optional[str] = Field(None, max_length=4000)
    background: bool = True


@router.get("/types")
def report_types(user: User = Depends(require_permissions(P.REPORT_GENERATE))):
    return {"types": reporting.REPORT_TYPES, "formats": reporting.FORMATS, "parameters": {"dataset_export": ["dataset_id", "variable_code?", "limit?"], "policy_indicators": ["policy_id?", "code?"], "simulation_run": ["run_id"], "analytics_run": ["run_id"], "gis_layer_summary": ["layer_id", "admin_unit_id?"], "evidence_trace": ["recommendation_id"], "repository_summary": [], "innovation_summary": []}}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_report(payload: ReportRequest, request: Request, user: User = Depends(require_permissions(P.REPORT_GENERATE)), db: Session = Depends(get_db)):
    report, job = reporting.create_report(db, title=payload.title, report_type=payload.report_type, fmt=payload.format, params=payload.parameters, methodology=payload.methodology, user=user, background=payload.background)
    audit.record(db, "report.create", user=user, resource_type="report", resource_id=report.id, detail={"type": payload.report_type, "format": payload.format}, request=request, commit=True)
    out = reporting.report_dict(report)
    out["job_id"] = str(job.id) if job else None
    return out


@router.get("")
def list_reports(page: PageParams = Depends(), mine: bool = True, user: User = Depends(require_permissions(P.REPORT_GENERATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    stmt = select(Report)
    if mine or not user.is_superuser:
        stmt = stmt.where(Report.created_by == user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Report.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([reporting.report_dict(r) for r in rows], total, page.page, page.page_size)


def _get(db: Session, rid: uuid.UUID, user: User) -> Report:
    r = db.get(Report, rid)
    if not r or (r.created_by != user.id and not user.is_superuser):
        raise NotFoundError("Report not found")
    return r


@router.get("/{rid}")
def get_report(rid: uuid.UUID, user: User = Depends(require_permissions(P.REPORT_GENERATE)), db: Session = Depends(get_db)):
    return reporting.report_dict(_get(db, rid, user))


@router.get("/{rid}/download")
def download(rid: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.REPORT_GENERATE)), db: Session = Depends(get_db)):
    r = _get(db, rid, user)
    if r.status != "ready" or not r.storage_key:
        raise ConflictError(f"Report is not ready (status={r.status})")
    mime = reporting.RENDERERS[r.format][1]
    audit.record(db, "report.download", user=user, resource_type="report", resource_id=r.id, request=request, commit=True)
    return StreamingResponse(get_storage().stream(r.storage_key), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{r.report_type}-{str(r.id)[:8]}.{r.format}"'})
