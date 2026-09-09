from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics import service as analytics
from app.api.deps import require_permissions
from app.audit import service as audit
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalysisRequest(BaseModel):
    analysis_type: str = Field(pattern="^(descriptive|trend|compare|correlation|anomaly|forecast|risk_score|timeseries|spatial_aggregate)$")
    title: Optional[str] = Field(None, max_length=255)
    workspace_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    variable_code: Optional[str] = Field(None, max_length=80)
    admin_unit_id: Optional[uuid.UUID] = None
    indicator_code: Optional[str] = Field(None, max_length=80)
    data: Optional[List[Dict[str, Any]]] = Field(None, max_length=20000, description="Inline rows: {year|x, value, label, value_kind}")
    dataset_version_id_y: Optional[uuid.UUID] = None
    variable_code_y: Optional[str] = None
    indicator_code_y: Optional[str] = None
    data_y: Optional[List[Dict[str, Any]]] = None
    horizon: int = Field(5, ge=1, le=30)
    alpha: float = Field(0.6, gt=0, lt=1)
    beta: float = Field(0.3, gt=0, lt=1)
    z_threshold: float = Field(2.5, gt=0)
    iqr_k: float = Field(1.5, gt=0)
    window: int = Field(3, ge=2, le=12)
    latest_only: bool = True
    level: str = Field("district", pattern="^(unit|country|state|district|subdistrict|village)$")
    year: Optional[int] = None
    indicators: Optional[List[Dict[str, Any]]] = Field(None, description="risk_score: [{code, weight, higher_is_riskier, values:[{label,value}]}]")


@router.get("/models")
def models(user: User = Depends(require_permissions(P.ANALYTICS_RUN)), db: Session = Depends(get_db)):
    return {"items": analytics.list_models(db), "analysis_types": analytics.ANALYSIS_TYPES}


@router.post("/run")
def run(payload: AnalysisRequest, request: Request, user: User = Depends(require_permissions(P.ANALYTICS_RUN)), db: Session = Depends(get_db)):
    params = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in payload.model_dump(exclude={"analysis_type", "title", "workspace_id"}, exclude_none=True).items()}
    result = analytics.run_analysis(db, analysis_type=payload.analysis_type, params=params, user_id=user.id, workspace_id=payload.workspace_id, title=payload.title)
    audit.record(db, "analytics.run", user=user, resource_type="analytics_run", resource_id=result["run_id"], detail={"type": payload.analysis_type}, request=request, commit=True)
    return result


@router.get("/runs")
def runs(mine: bool = True, limit: Annotated[int, Query(le=200)] = 50, user: User = Depends(require_permissions(P.ANALYTICS_RUN)), db: Session = Depends(get_db)):
    return {"items": analytics.list_runs(db, user.id if mine else None, limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, user: User = Depends(require_permissions(P.ANALYTICS_RUN)), db: Session = Depends(get_db)):
    return analytics.get_run(db, run_id)
