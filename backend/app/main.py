from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import settings
from app.core.exceptions import install_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware, SecureHeadersMiddleware
from app.db.database import SessionLocal

logger = get_logger("bhoomitra")

DESCRIPTION = """
**Bhoomitra** — National Digital Platform for Research, Policy Innovation and Evidence-Based Land Governance
(Department of Land Resources, Ministry of Rural Development — PME Division).

All decision-support outputs (AI answers, analytics, simulations) carry evidence provenance and are **not**
official government decisions. Records flagged `is_demo: true` are *Demo / Synthetic Data*.
"""


def build_v1_router() -> APIRouter:
    from app.api.v1 import admin, analytics, auth, dashboards, datasets, documents, gis, innovation, integrations, knowledge_ai, notifications, organizations, reports, research, simulations, users, workspaces

    v1 = APIRouter()
    v1.include_router(auth.router)
    v1.include_router(users.router)
    v1.include_router(organizations.router)
    v1.include_router(documents.router)
    v1.include_router(research.research_router)
    v1.include_router(research.policy_router)
    v1.include_router(datasets.router)
    v1.include_router(knowledge_ai.search_router)
    v1.include_router(knowledge_ai.ai_router)
    v1.include_router(knowledge_ai.evidence_router)
    v1.include_router(gis.router)
    v1.include_router(gis.rs_router)
    v1.include_router(analytics.router)
    v1.include_router(simulations.router)
    v1.include_router(workspaces.router)
    v1.include_router(innovation.router)
    v1.include_router(innovation.challenges_router)
    v1.include_router(innovation.submissions_router)
    v1.include_router(dashboards.router)
    v1.include_router(reports.router)
    v1.include_router(integrations.router)
    v1.include_router(notifications.router)
    v1.include_router(admin.router)
    v1.include_router(admin.audit_router)
    return v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from app.workers.dispatch import import_task_modules

    import_task_modules()
    if settings.app_env != "test":
        db = SessionLocal()
        try:
            from app.seed.bootstrap import bootstrap

            bootstrap(db)
        except Exception as exc:  # pragma: no cover - surfaced via readiness
            logger.error("bootstrap failed", extra={"extra_data": {"error": str(exc)[:300]}})
        finally:
            db.close()
    logger.info("startup", extra={"extra_data": {"env": settings.app_env, "tasks": settings.task_execution_mode, "storage": settings.storage_backend, "ai": settings.ai_provider, "embeddings": settings.embedding_provider}})
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(SecureHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Requested-With"],
        expose_headers=["X-Request-ID", "Content-Disposition", "X-Checksum-SHA256"],
    )
    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(build_v1_router(), prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": settings.app_name, "status": "running", "version": settings.app_version, "api": settings.api_v1_prefix, "docs": "/docs"}

    return app


app = create_app()
