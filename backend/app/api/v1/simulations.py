from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_permissions, require_permissions
from app.audit import service as audit
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.intelligence import Scenario, ScenarioStatus, SimulationRun
from app.schemas.common import Page, PageParams
from app.simulation import engine
from app.workers.dispatch import enqueue

router = APIRouter(prefix="/simulations", tags=["simulations"])


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    baseline: Dict[str, Any] = Field(default_factory=dict, description="{land_km2:{cropland,forest,grassland,built_up,water,wasteland}, population_k, rainfall_mm, base_year}")
    interventions: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: Optional[Dict[str, Any]] = None
    horizon_years: int = Field(10, ge=1, le=50)
    admin_unit_id: Optional[uuid.UUID] = None
    baseline_layer_id: Optional[uuid.UUID] = Field(None, description="Derive baseline land classes from this land-cover layer (OBSERVED)")
    baseline_dataset_version_id: Optional[uuid.UUID] = None
    workspace_id: Optional[uuid.UUID] = None
    parent_scenario_id: Optional[uuid.UUID] = None
    assumptions: Optional[List[Dict[str, Any]]] = None


class RunRequest(BaseModel):
    iterations: int = Field(500, ge=50, le=5000)
    seed: Optional[int] = Field(None, ge=0)
    background: bool = False


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject|submit|return)$")
    note: Optional[str] = Field(None, max_length=4000)


@router.get("/model")
def model_card(user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_RUN, any_of=True)), db: Session = Depends(get_db)):
    mv = engine.ensure_model(db)
    return {"model_version_id": str(mv.id), "version": mv.version, "algorithm": mv.algorithm, "features": mv.features, "limitations": mv.limitations, "coefficients": engine.DEFAULT_COEFFICIENTS, "indicators": [{"code": c, "label": l, "unit": u, "domain": d} for c, l, u, d in engine.INDICATORS], "land_classes": engine.LAND_CLASSES, "intervention_types": ["reallocate", "yield_improvement", "irrigation_expansion", "rainfall_shift"], "value_kinds": ["OBSERVED", "MODELLED", "ASSUMPTION", "SCENARIO", "UNCERTAINTY"]}


@router.get("/scenarios")
def list_scenarios(page: PageParams = Depends(), status_filter: Annotated[Optional[ScenarioStatus], Query(alias="status")] = None, mine: bool = False, workspace_id: Optional[uuid.UUID] = None, user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_RUN, P.SIMULATION_APPROVE, any_of=True)), db: Session = Depends(get_db)):
    stmt = select(Scenario)
    if status_filter:
        stmt = stmt.where(Scenario.status == status_filter)
    if mine:
        stmt = stmt.where(Scenario.created_by == user.id)
    if workspace_id:
        stmt = stmt.where(Scenario.workspace_id == workspace_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Scenario.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    items = [{k: v for k, v in engine.scenario_dict(s, db).items() if k != "assumptions"} for s in rows]
    return Page.build(items, total, page.page, page.page_size)


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, request: Request, user: User = Depends(require_permissions(P.SIMULATION_CREATE)), db: Session = Depends(get_db)):
    sc = engine.create_scenario(db, name=payload.name, description=payload.description, baseline=payload.baseline, interventions=payload.interventions, constraints=payload.constraints, horizon_years=payload.horizon_years, admin_unit_id=payload.admin_unit_id, baseline_layer_id=payload.baseline_layer_id, baseline_dataset_version_id=payload.baseline_dataset_version_id, workspace_id=payload.workspace_id, parent_scenario_id=payload.parent_scenario_id, user_id=user.id, extra_assumptions=payload.assumptions)
    audit.record(db, "simulation.scenario_create", user=user, resource_type="scenario", resource_id=sc.id, request=request, commit=True)
    return engine.scenario_dict(sc, db)


@router.get("/scenarios/{sid}")
def get_scenario(sid: uuid.UUID, user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_RUN, P.SIMULATION_APPROVE, any_of=True)), db: Session = Depends(get_db)):
    return engine.scenario_dict(engine.get_scenario(db, sid), db)


@router.post("/scenarios/{sid}/run")
def run_scenario(sid: uuid.UUID, payload: RunRequest, request: Request, user: User = Depends(require_permissions(P.SIMULATION_RUN)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    sc = engine.get_scenario(db, sid)
    if sc.created_by != user.id and P.SIMULATION_APPROVE not in perms and not user.is_superuser:
        raise ForbiddenError("You can only run your own scenarios")
    if payload.background:
        job = enqueue(db, "simulation.run", target_type="scenario", target_id=sc.id, payload={"scenario_id": str(sc.id), "iterations": payload.iterations, "seed": payload.seed}, created_by=user.id)
        return {"job_id": str(job.id), "status": job.status, "scenario_id": str(sc.id)}
    run = engine.run_scenario(db, sc, iterations=payload.iterations, seed=payload.seed, user_id=user.id)
    audit.record(db, "simulation.run", user=user, resource_type="simulation_run", resource_id=run.id, detail={"scenario": str(sc.id), "iterations": payload.iterations}, request=request, commit=True)
    return engine.run_dict(db, run)


@router.post("/scenarios/{sid}/review")
def review_scenario(sid: uuid.UUID, payload: ReviewRequest, request: Request, user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_APPROVE, any_of=True)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    sc = engine.get_scenario(db, sid)
    if payload.decision in ("approve", "reject") and P.SIMULATION_APPROVE not in perms and not user.is_superuser:
        raise ForbiddenError("simulation.approve permission required")
    target = {"submit": ScenarioStatus.UNDER_REVIEW, "return": ScenarioStatus.SIMULATED, "approve": ScenarioStatus.APPROVED, "reject": ScenarioStatus.REJECTED}[payload.decision]
    sc = engine.transition(db, sc, target, user.id, payload.note)
    audit.record(db, f"simulation.scenario_{payload.decision}", user=user, resource_type="scenario", resource_id=sc.id, detail={"note": payload.note}, request=request, commit=True)
    return engine.scenario_dict(sc, db)


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, series: bool = True, user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_RUN, P.SIMULATION_APPROVE, any_of=True)), db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if not run:
        raise NotFoundError("Run not found")
    return engine.run_dict(db, run, include_series=series)


@router.get("/compare")
def compare(run_ids: Annotated[str, Query(description="comma separated run ids")], user: User = Depends(require_permissions(P.SIMULATION_CREATE, P.SIMULATION_RUN, P.SIMULATION_APPROVE, any_of=True)), db: Session = Depends(get_db)):
    ids = [uuid.UUID(r.strip()) for r in run_ids.split(",") if r.strip()][:6]
    return engine.compare_runs(db, ids)


class BaselinePreview(BaseModel):
    layer_id: uuid.UUID
    admin_unit_id: Optional[uuid.UUID] = None


@router.post("/baseline/from-layer")
def baseline_from_layer(payload: BaselinePreview, user: User = Depends(require_permissions(P.SIMULATION_CREATE)), db: Session = Depends(get_db)):
    return engine.baseline_from_layer(db, payload.layer_id, payload.admin_unit_id)
