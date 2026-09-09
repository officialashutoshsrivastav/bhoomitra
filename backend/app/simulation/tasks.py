from __future__ import annotations

import uuid
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.platform import BackgroundJob
from app.simulation import engine
from app.workers.dispatch import register_job


@register_job("simulation.run")
def _job_run_simulation(db: Session, job: BackgroundJob) -> Dict[str, Any]:
    sc = engine.get_scenario(db, uuid.UUID(str(job.payload["scenario_id"])))
    run = engine.run_scenario(db, sc, iterations=int(job.payload.get("iterations", 500)), seed=job.payload.get("seed"), user_id=job.created_by)
    return {"run_id": str(run.id), "status": run.status}
