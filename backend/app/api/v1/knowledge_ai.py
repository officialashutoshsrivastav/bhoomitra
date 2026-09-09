from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import rag
from app.api.deps import get_current_user, get_current_user_optional, get_permissions, load_user_permissions, require_permissions
from app.audit import service as audit
from app.core.exceptions import NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.intelligence import NodeType, Recommendation
from app.models.platform import SavedSearch
from app.schemas.common import Message
from app.search import service as search
from app.services import evidence_service

search_router = APIRouter(prefix="/search", tags=["search"])
ai_router = APIRouter(prefix="/ai", tags=["ai"])
evidence_router = APIRouter(prefix="/evidence", tags=["evidence"])


def _perms_for(request: Request, user: Optional[User], db: Session) -> set:
    if user is None:
        return set()
    return getattr(request.state, "permissions", None) or load_user_permissions(db, user)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@search_router.get("")
def global_search(
    request: Request,
    q: Annotated[str, Query(max_length=300)] = "",
    types: Annotated[Optional[str], Query(description="Comma separated: document,dataset,policy,research_project,challenge")] = None,
    topic: Optional[str] = None,
    geography: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    document_type: Optional[str] = None,
    organization_id: Optional[uuid.UUID] = None,
    policy_area: Optional[str] = None,
    research_area: Optional[str] = None,
    language: Optional[str] = None,
    source: Optional[str] = None,
    include_demo: bool = True,
    sort: Annotated[str, Query(pattern="^(relevance|date|title)$")] = "relevance",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    perms = _perms_for(request, user, db)
    f = search.SearchFilters(entity_types=[t.strip() for t in types.split(",") if t.strip()] if types else None, topic=topic, geography=geography, date_from=date_from, date_to=date_to, document_type=document_type, organization_id=organization_id, policy_area=policy_area, research_area=research_area, language=language, source=source, include_demo=include_demo)
    hits, total, info = search.hybrid_search(db, q, f, user, perms, page, page_size, sort)
    filters_used = {k: (str(v) if v is not None else None) for k, v in f.__dict__.items() if v not in (None, True, False, [])}
    search.record_history(db, user, q, filters_used, total)
    return {
        "query": q,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "relevance": info,
        "items": [
            {"entity_type": h.entity_type, "id": h.entity_id, "title": h.title, "snippet": h.snippet, "score": round(h.score, 5), "matched_by": h.matched_by, "keyword_score": h.keyword_score, "vector_score": h.vector_score, "keyword_rank": h.keyword_rank, "vector_rank": h.vector_rank, "is_demo": h.is_demo, "metadata": h.metadata}
            for h in hits
        ],
    }


@search_router.get("/autocomplete")
def autocomplete(request: Request, q: Annotated[str, Query(min_length=1, max_length=100)], user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    return {"suggestions": search.autocomplete(db, q, user, _perms_for(request, user, db))}


@search_router.get("/facets")
def facets(request: Request, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    return search.facets(db, user, _perms_for(request, user, db))


@search_router.get("/recent")
def recent(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"items": search.recent_searches(db, user)}


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    query: str = Field(max_length=500)
    filters: Optional[Dict[str, Any]] = None


@search_router.get("/saved")
def list_saved(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.created_at.desc())).all()
    return {"items": [{"id": str(s.id), "name": s.name, "query": s.query, "filters": s.filters, "created_at": s.created_at.isoformat()} for s in rows]}


@search_router.post("/saved", status_code=status.HTTP_201_CREATED)
def save_search(payload: SavedSearchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = SavedSearch(user_id=user.id, **payload.model_dump())
    db.add(s)
    db.commit()
    return {"id": str(s.id), "name": s.name, "query": s.query, "filters": s.filters}


@search_router.delete("/saved/{saved_id}", response_model=Message)
def delete_saved(saved_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(SavedSearch, saved_id)
    if not s or s.user_id != user.id:
        raise NotFoundError("Saved search not found")
    db.delete(s)
    db.commit()
    return Message(message="Deleted")


# ---------------------------------------------------------------------------
# AI assistant
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    conversation_id: Optional[uuid.UUID] = None
    document_ids: Optional[List[uuid.UUID]] = Field(None, max_length=20, description="Restrict retrieval to these documents")
    workspace_id: Optional[uuid.UUID] = None


@ai_router.post("/ask")
def ask(payload: AskRequest, request: Request, user: User = Depends(require_permissions(P.AI_QUERY)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    result = rag.ask(db, user, perms, payload.question, payload.conversation_id, payload.document_ids, payload.workspace_id)
    audit.record(db, "ai.ask", user=user, resource_type="ai_message", resource_id=result["message_id"], detail={"sufficient": result["evidence_sufficient"], "confidence": result["confidence"], "provider": result["provider"]}, request=request, commit=True)
    return result


@ai_router.get("/conversations")
def conversations(user: User = Depends(require_permissions(P.AI_QUERY)), db: Session = Depends(get_db)):
    return {"items": rag.list_conversations(db, user)}


@ai_router.get("/conversations/{conv_id}")
def conversation(conv_id: uuid.UUID, user: User = Depends(require_permissions(P.AI_QUERY)), db: Session = Depends(get_db)):
    return rag.get_conversation(db, user, conv_id)


@ai_router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    from app.ai.embeddings import get_embedding_provider
    from app.ai.llm import get_llm_provider
    from app.core.config import settings

    return {"llm": {"provider": get_llm_provider().name, "model": get_llm_provider().model_name, "mode": "live" if settings.ai_provider == "openai" else "extractive-fallback"}, "embeddings": {"provider": get_embedding_provider().name, "model": get_embedding_provider().model_name, "dim": get_embedding_provider().dim}, "retrieval": {"top_k": settings.rag_top_k, "min_score": settings.rag_min_score, "vector_store": "pgvector", "keyword": "opensearch+postgres_fts"}}


# ---------------------------------------------------------------------------
# Evidence engine
# ---------------------------------------------------------------------------
@evidence_router.get("/recommendations")
def list_recommendations(kind: Optional[str] = None, limit: Annotated[int, Query(ge=1, le=200)] = 30, user: User = Depends(require_permissions(P.EVIDENCE_READ)), db: Session = Depends(get_db)):
    stmt = select(Recommendation).order_by(Recommendation.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(Recommendation.kind == kind)
    rows = db.scalars(stmt).all()
    return {"items": [{"id": str(r.id), "kind": r.kind, "title": r.title, "confidence": r.confidence, "is_demo": r.is_demo, "created_at": r.created_at.isoformat(), "evidence_count": len(r.evidence)} for r in rows]}


@evidence_router.get("/{rec_id}")
def get_recommendation(rec_id: uuid.UUID, user: User = Depends(require_permissions(P.EVIDENCE_READ)), db: Session = Depends(get_db)):
    return evidence_service.explain(db, evidence_service.get_recommendation(db, rec_id))


@evidence_router.get("/{rec_id}/trace")
def trace(rec_id: uuid.UUID, depth: Annotated[int, Query(ge=1, le=10)] = 6, user: User = Depends(require_permissions(P.EVIDENCE_READ)), db: Session = Depends(get_db)):
    evidence_service.get_recommendation(db, rec_id)
    return evidence_service.trace(db, NodeType.RECOMMENDATION, rec_id, max_depth=depth)


@evidence_router.get("/node/{node_type}/{node_id}/trace")
def node_trace(node_type: NodeType, node_id: uuid.UUID, depth: Annotated[int, Query(ge=1, le=10)] = 5, user: User = Depends(require_permissions(P.EVIDENCE_READ)), db: Session = Depends(get_db)):
    return evidence_service.trace(db, node_type, node_id, max_depth=depth)
