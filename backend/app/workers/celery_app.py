from __future__ import annotations

import uuid

from celery import Celery

from app.core.config import settings

broker = settings.effective_celery_broker or "memory://"
backend = settings.celery_result_backend or settings.redis_url or "cache+memory://"

celery_app = Celery("bhoomitra", broker=broker, backend=backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    task_default_queue="bhoomitra",
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.app_env == "test" and settings.task_execution_mode != "celery",
)


@celery_app.task(name="bhoomitra.execute_job", bind=True, max_retries=0)
def execute_job_task(self, job_id: str):
    from app.core.logging import configure_logging
    from app.workers.dispatch import import_task_modules, run_job

    configure_logging()
    import_task_modules()
    return run_job(uuid.UUID(job_id))


@celery_app.task(name="bhoomitra.heartbeat")
def heartbeat():
    return {"ok": True}


celery_app.conf.beat_schedule = {
    "worker-heartbeat": {"task": "bhoomitra.heartbeat", "schedule": 60.0},
}
