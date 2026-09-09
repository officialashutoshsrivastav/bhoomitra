from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.platform import BackgroundJob

logger = get_logger("bhoomitra.workers")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bm-job")
_registry: Dict[str, Callable[[Session, BackgroundJob], Dict[str, Any]]] = {}
_lock = threading.Lock()
_inflight = 0


def register_job(job_type: str):
    def deco(fn: Callable[[Session, BackgroundJob], Dict[str, Any]]):
        _registry[job_type] = fn
        return fn

    return deco


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db: Session, job_type: str, *, target_type: Optional[str] = None, target_id: Optional[uuid.UUID] = None, payload: Optional[Dict[str, Any]] = None, created_by: Optional[uuid.UUID] = None, max_retries: int = 3) -> BackgroundJob:
    job = BackgroundJob(job_type=job_type, target_type=target_type, target_id=target_id, payload=payload or {}, created_by=created_by, max_retries=max_retries, status="queued")
    db.add(job)
    db.flush()
    return job


def run_job(job_id: uuid.UUID) -> Dict[str, Any]:
    """Execute a job by id in its own DB session. Used by Celery and thread modes."""
    global _inflight
    with _lock:
        _inflight += 1
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job:
            return {"error": "job not found"}
        fn = _registry.get(job.job_type)
        if fn is None:
            job.status = "failed"
            job.error = f"No handler registered for {job.job_type}"
            db.commit()
            return {"error": job.error}
        job.status = "running"
        job.started_at = _now()
        job.error = None
        db.commit()
        try:
            result = fn(db, job)
            job.status = "completed"
            job.progress = 100
            job.result = result
            job.completed_at = _now()
            db.commit()
            return result
        except Exception as exc:
            db.rollback()
            job = db.get(BackgroundJob, job_id)
            job.retry_count = (job.retry_count or 0) + 1
            job.error = f"{type(exc).__name__}: {exc}"[:2000]
            logger.error("job failed", extra={"extra_data": {"job": str(job_id), "type": job.job_type, "error": job.error, "trace": traceback.format_exc()[-1500:]}})
            if job.retry_count <= job.max_retries:
                job.status = "queued"
                db.commit()
                _dispatch_later(job.id)
            else:
                job.status = "failed"
                job.completed_at = _now()
                db.commit()
            return {"error": job.error}
    finally:
        db.close()
        with _lock:
            _inflight -= 1


def _dispatch_later(job_id: uuid.UUID) -> None:
    mode = settings.task_execution_mode
    if mode == "celery":
        from app.workers.celery_app import execute_job_task

        execute_job_task.apply_async(args=[str(job_id)], countdown=5)
    elif mode == "thread":
        _executor.submit(run_job, job_id)
    else:
        run_job(job_id)


def dispatch(db: Session, job: BackgroundJob) -> BackgroundJob:
    """Send a queued job for execution according to TASK_EXECUTION_MODE."""
    db.commit()
    mode = settings.task_execution_mode
    if mode == "celery":
        from app.workers.celery_app import execute_job_task

        async_result = execute_job_task.delay(str(job.id))
        job.celery_task_id = async_result.id
        db.commit()
    elif mode == "thread":
        _executor.submit(run_job, job.id)
    else:
        run_job(job.id)
        db.expire_all()
    return job


def enqueue(db: Session, job_type: str, **kwargs) -> BackgroundJob:
    job = create_job(db, job_type, **kwargs)
    return dispatch(db, job)


def worker_status() -> Dict[str, Any]:
    mode = settings.task_execution_mode
    if mode == "celery":
        try:
            from app.workers.celery_app import celery_app

            insp = celery_app.control.inspect(timeout=1.0)
            pong = insp.ping() if insp else None
            return {"ok": bool(pong), "mode": "celery", "workers": list(pong.keys()) if pong else [], "note": None if pong else "No Celery workers responded to ping"}
        except Exception as exc:
            return {"ok": False, "mode": "celery", "error": str(exc)[:200]}
    return {"ok": True, "mode": mode, "inflight": _inflight, "note": "In-process execution; run a Celery worker with TASK_EXECUTION_MODE=celery for production"}


def import_task_modules() -> None:
    import app.ingestion.tasks  # noqa: F401
    import app.reporting.tasks  # noqa: F401
    import app.simulation.tasks  # noqa: F401
    import app.search.tasks  # noqa: F401
