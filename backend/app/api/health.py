from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.storage.service import get_storage

router = APIRouter(tags=["health"])
_started = time.time()


def check_database(db: Session) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        postgis = db.execute(text("SELECT extversion FROM pg_extension WHERE extname='postgis'")).scalar()
        vector = db.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
        return {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "postgis": postgis, "pgvector": vector}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def check_redis() -> Dict[str, Any]:
    if not settings.redis_url:
        return {"ok": True, "configured": False, "note": "Redis not configured; in-memory cache/rate limits in use"}
    try:
        import redis

        r = redis.Redis.from_url(settings.redis_url, socket_timeout=1)
        t0 = time.perf_counter()
        r.ping()
        return {"ok": True, "configured": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": str(exc)[:200]}


def check_opensearch() -> Dict[str, Any]:
    from app.search.opensearch_client import opensearch_status

    return opensearch_status()


def check_storage() -> Dict[str, Any]:
    ok, msg = get_storage().health()
    return {"ok": ok, "backend": settings.storage_backend, "detail": msg}


def check_workers() -> Dict[str, Any]:
    from app.workers.dispatch import worker_status

    return worker_status()


def check_ai() -> Dict[str, Any]:
    return {"ok": True, "llm_provider": settings.ai_provider, "embedding_provider": settings.embedding_provider, "embedding_dim": settings.embedding_dim, "mode": "live" if settings.ai_provider == "openai" else "local-extractive (no external LLM configured)"}


@router.get("/health")
def health():
    return {"status": "healthy", "app": settings.app_name, "version": settings.app_version, "env": settings.app_env, "uptime_s": int(time.time() - _started)}


@router.get("/health/live")
def live():
    return {"status": "alive"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    checks = {"database": check_database(db), "redis": check_redis(), "opensearch": check_opensearch(), "storage": check_storage(), "workers": check_workers(), "ai": check_ai()}
    critical_ok = checks["database"]["ok"] and checks["storage"]["ok"]
    body = {"status": "ready" if critical_ok else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if critical_ok else 503, content=body)


@router.get("/health/database")
def database_health(db: Session = Depends(get_db)):
    version = db.execute(text("SELECT version()")).scalar()
    return {"status": "connected", "database": "PostgreSQL", "version": version, **check_database(db)}
