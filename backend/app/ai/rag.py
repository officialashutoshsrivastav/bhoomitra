from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.embeddings import tokenize
from app.ai.llm import Passage, get_llm_provider
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.datasets import Dataset, DatasetStatus
from app.models.gis import AdminUnit, GISLayer
from app.models.identity import User
from app.models.intelligence import AIConversation, AIMessage, Citation, NodeType
from app.models.knowledge import Document, DocumentChunk, Policy
from app.search.service import SearchFilters, keyword_documents, vector_chunks
from app.services import evidence_service

_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_INTENTS = {
    "comparison": ["compare", "versus", "vs", "difference", "better"],
    "trend": ["trend", "change", "over time", "growth", "decline", "increase", "decrease"],
    "definition": ["what is", "define", "meaning", "explain"],
    "policy": ["policy", "act", "rule", "scheme", "guideline", "framework", "regulation"],
    "spatial": ["district", "state", "village", "map", "where", "region", "area"],
    "statistic": ["how many", "how much", "percentage", "rate", "number of", "statistics"],
}
_POLICY_AREAS = ["land use", "land acquisition", "land records", "agriculture", "forest", "water", "urban", "climate", "disaster", "rural development", "tenure", "watershed", "wasteland"]


@dataclass
class QueryAnalysis:
    normalized: str
    intents: List[str]
    years: List[int]
    geography_terms: List[str]
    policy_areas: List[str]
    keywords: List[str]
    filters: Dict[str, Any] = field(default_factory=dict)


def analyze_query(db: Session, question: str) -> QueryAnalysis:
    q = question.strip()
    lower = q.lower()
    intents = [name for name, cues in _INTENTS.items() if any(c in lower for c in cues)] or ["general"]
    years = [int(y) for y in _YEAR_RE.findall(q)]
    geo = []
    names = db.scalars(select(AdminUnit.name).where(AdminUnit.level.in_(["state", "district"])).limit(2000)).all()
    for n in names:
        if n and n.lower() in lower:
            geo.append(n)
    areas = [a for a in _POLICY_AREAS if a in lower]
    keywords = tokenize(q)[:12]
    filters: Dict[str, Any] = {}
    if geo:
        filters["geography"] = geo[0]
    return QueryAnalysis(normalized=q, intents=intents, years=years, geography_terms=geo, policy_areas=areas, keywords=keywords, filters=filters)


@dataclass
class RetrievedChunk:
    chunk: DocumentChunk
    document: Document
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0


def _lexical_overlap(query_terms: Set[str], text: str) -> float:
    if not query_terms:
        return 0.0
    terms = set(tokenize(text))
    return len(query_terms & terms) / len(query_terms)


def retrieve(db: Session, qa: QueryAnalysis, user: User, perms: Set[str], top_k: int, document_ids: Optional[List[uuid.UUID]] = None) -> Tuple[List[RetrievedChunk], Dict[str, Any]]:
    filters = SearchFilters(geography=None)
    # vector retrieval on chunks
    vec_rows = vector_chunks(db, qa.normalized, filters, user, perms, limit=top_k * 4, document_ids=document_ids)
    # keyword retrieval on documents → expand to their best chunks by FTS rank
    kw_hits = keyword_documents(db, qa.normalized, filters, user, perms, limit=top_k * 2)
    kw_doc_ids = [uuid.UUID(h.entity_id) for h in kw_hits]
    if document_ids:
        kw_doc_ids = [d for d in kw_doc_ids if d in document_ids]
    kw_chunks: List[Tuple[DocumentChunk, Document, float]] = []
    if kw_doc_ids:
        tsq = func.websearch_to_tsquery("english", qa.normalized)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsq)
        stmt = select(DocumentChunk, Document, rank).join(Document, Document.id == DocumentChunk.document_id).where(DocumentChunk.document_id.in_(kw_doc_ids), DocumentChunk.version_id == Document.current_version_id, DocumentChunk.search_vector.op("@@")(tsq)).order_by(rank.desc()).limit(top_k * 3)
        kw_chunks = [(c, d, float(r or 0)) for c, d, r in db.execute(stmt).all()]

    merged: Dict[uuid.UUID, RetrievedChunk] = {}
    for c, d, s in vec_rows:
        rc = merged.setdefault(c.id, RetrievedChunk(chunk=c, document=d))
        rc.vector_score = max(rc.vector_score, s)
    for c, d, s in kw_chunks:
        rc = merged.setdefault(c.id, RetrievedChunk(chunk=c, document=d))
        rc.keyword_score = max(rc.keyword_score, s)

    # re-ranking: weighted blend of normalised vector sim, normalised keyword rank and lexical overlap
    q_terms = set(qa.keywords)
    max_kw = max((r.keyword_score for r in merged.values()), default=0.0) or 1.0
    for r in merged.values():
        overlap = _lexical_overlap(q_terms, r.chunk.content)
        geo_boost = 0.05 if qa.geography_terms and r.document.geography and any(g.lower() in (r.document.geography or "").lower() for g in qa.geography_terms) else 0.0
        year_boost = 0.03 if qa.years and r.document.publication_date and r.document.publication_date.year in qa.years else 0.0
        r.rerank_score = 0.55 * max(r.vector_score, 0.0) + 0.25 * (r.keyword_score / max_kw) + 0.20 * overlap + geo_boost + year_boost
    ranked = sorted(merged.values(), key=lambda r: -r.rerank_score)
    # evidence selection: cap per document to encourage source diversity
    selected: List[RetrievedChunk] = []
    per_doc: Dict[uuid.UUID, int] = {}
    for r in ranked:
        if per_doc.get(r.document.id, 0) >= 3:
            continue
        if r.rerank_score < settings.rag_min_score:
            continue
        selected.append(r)
        per_doc[r.document.id] = per_doc.get(r.document.id, 0) + 1
        if len(selected) >= top_k:
            break
    stats = {"vector_candidates": len(vec_rows), "keyword_documents": len(kw_hits), "keyword_chunks": len(kw_chunks), "merged": len(merged), "selected": len(selected), "top_score": round(selected[0].rerank_score, 4) if selected else 0.0}
    return selected, stats


def related_resources(db: Session, qa: QueryAnalysis, user: User, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    like_terms = [t for t in qa.keywords if len(t) > 3][:5]
    out: Dict[str, List[Dict[str, Any]]] = {"datasets": [], "policies": [], "maps": []}
    if like_terms:
        conds = [or_(Dataset.name.ilike(f"%{t}%"), Dataset.description.ilike(f"%{t}%")) for t in like_terms]
        for ds in db.scalars(select(Dataset).where(Dataset.deleted_at.is_(None), or_(*conds)).limit(limit)).all():
            out["datasets"].append({"id": str(ds.id), "name": ds.name, "category": ds.category.value, "is_demo": ds.is_demo, "status": ds.status.value})
        conds = [or_(Policy.title.ilike(f"%{t}%"), Policy.summary.ilike(f"%{t}%")) for t in like_terms]
        for p in db.scalars(select(Policy).where(Policy.deleted_at.is_(None), or_(*conds)).limit(limit)).all():
            out["policies"].append({"id": str(p.id), "title": p.title, "policy_area": p.policy_area, "is_demo": p.is_demo})
        conds = [or_(GISLayer.name.ilike(f"%{t}%"), GISLayer.description.ilike(f"%{t}%")) for t in like_terms]
        for layer in db.scalars(select(GISLayer).where(or_(*conds)).limit(limit)).all():
            out["maps"].append({"id": str(layer.id), "name": layer.name, "category": layer.category.value, "is_demo": layer.is_demo})
    return out


def _confidence(selected: List[RetrievedChunk], used_markers: List[int]) -> Tuple[float, str]:
    if not selected:
        return 0.0, "No evidence retrieved"
    top = selected[0].rerank_score
    coverage = len(used_markers) / max(1, min(len(selected), 4))
    distinct_docs = len({r.document.id for r in selected})
    conf = min(1.0, 0.5 * min(top / 0.6, 1.0) + 0.3 * min(coverage, 1.0) + 0.2 * min(distinct_docs / 3, 1.0))
    basis = f"top relevance {top:.2f}, {len(used_markers)} cited passage(s), {distinct_docs} distinct source document(s)"
    return round(conf, 3), basis


def ask(db: Session, user: User, perms: Set[str], question: str, conversation_id: Optional[uuid.UUID] = None, document_ids: Optional[List[uuid.UUID]] = None, workspace_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    conv = db.get(AIConversation, conversation_id) if conversation_id else None
    if conversation_id and (not conv or conv.user_id != user.id):
        raise NotFoundError("Conversation not found")
    if conv is None:
        conv = AIConversation(user_id=user.id, title=question[:120], workspace_id=workspace_id)
        db.add(conv)
        db.flush()
    history = [{"role": m.role, "content": m.content} for m in conv.messages[-6:]]
    db.add(AIMessage(conversation_id=conv.id, role="user", content=question))
    db.flush()

    qa = analyze_query(db, question)
    selected, stats = retrieve(db, qa, user, perms, settings.rag_top_k, document_ids)
    passages = [Passage(marker=i + 1, text=r.chunk.content, title=r.document.title, locator=f"p.{r.chunk.page_start}" if r.chunk.page_start else f"chunk {r.chunk.chunk_index}") for i, r in enumerate(selected)]
    sufficient = bool(selected) and selected[0].rerank_score >= max(settings.rag_min_score * 2, 0.12)
    limitations = []
    if not sufficient:
        limitations.append("Retrieved evidence is weak or absent; treat the answer as not established.")
    demo_used = any(r.document.is_demo for r in selected)
    if demo_used:
        limitations.append("One or more sources are Demo / Synthetic Data.")

    if sufficient:
        gen = get_llm_provider().answer(question, passages, history)
        answer = gen.answer
        used = gen.used_markers
        provider, model_name = gen.provider, gen.model_name
        if gen.inference_note:
            limitations.append(gen.inference_note)
    else:
        provider, model_name, used = "none", "n/a", []
        answer = "I could not find sufficient evidence in the repository to answer this question reliably. " + ("The closest passages were only weakly related. " if selected else "No relevant passages were retrieved. ") + "Consider rephrasing, adding a geography or year, or uploading the relevant documents."
    conf, basis = _confidence(selected, used) if sufficient else (0.0, "insufficient evidence")

    rec = evidence_service.create_recommendation(db, kind="ai_answer", title=question[:200], statement=answer, created_by=user.id, confidence=conf, confidence_basis=basis, limitations=" ".join(limitations) or None, is_demo=demo_used)
    msg = AIMessage(conversation_id=conv.id, role="assistant", content=answer, query_analysis=qa.__dict__, retrieval=stats, provider=provider, model_name=model_name, confidence=conf, evidence_sufficient=sufficient, limitations=" ".join(limitations) or None, recommendation_id=rec.id, latency_ms=int((time.perf_counter() - t0) * 1000))
    db.add(msg)
    db.flush()
    evidence_service.link(db, NodeType.AI_MESSAGE, msg.id, NodeType.RECOMMENDATION, rec.id, "produced")

    citations_out = []
    for i, r in enumerate(selected):
        marker = i + 1
        cited = marker in used
        ev = evidence_service.add_evidence(db, rec, source_type=NodeType.DOCUMENT_CHUNK, source_id=r.chunk.id, label=f"[{marker}] {r.document.title}", excerpt=r.chunk.content[:600], locator=f"page {r.chunk.page_start}" if r.chunk.page_start else None, score=round(r.rerank_score, 4), value_kind="OBSERVED", rank=marker)
        db.add(Citation(message_id=msg.id, document_id=r.document.id, chunk_id=r.chunk.id, marker=marker, excerpt=r.chunk.content[:400], page=r.chunk.page_start, score=round(r.rerank_score, 4)))
        citations_out.append({"marker": marker, "document_id": str(r.document.id), "document_title": r.document.title, "document_type": r.document.type if hasattr(r.document, "type") else r.document.document_type.value, "chunk_id": str(r.chunk.id), "page": r.chunk.page_start, "excerpt": r.chunk.content[:400], "score": round(r.rerank_score, 4), "vector_score": round(r.vector_score, 4), "keyword_score": round(r.keyword_score, 4), "cited_in_answer": cited, "is_demo": r.document.is_demo, "evidence_id": str(ev.id)})
    db.commit()

    return {
        "conversation_id": str(conv.id),
        "message_id": str(msg.id),
        "recommendation_id": str(rec.id),
        "answer": answer,
        "evidence_sufficient": sufficient,
        "confidence": conf,
        "confidence_basis": basis,
        "limitations": limitations,
        "provider": provider,
        "model_name": model_name,
        "query_analysis": {"intents": qa.intents, "years": qa.years, "geography": qa.geography_terms, "policy_areas": qa.policy_areas, "keywords": qa.keywords},
        "retrieval": stats,
        "citations": citations_out,
        "sources": [{"document_id": c["document_id"], "title": c["document_title"], "is_demo": c["is_demo"]} for c in {c["document_id"]: c for c in citations_out}.values()],
        "related": related_resources(db, qa, user),
        "disclaimer": "Decision-support output generated from repository evidence. Not an official government position.",
        "latency_ms": msg.latency_ms,
    }


def list_conversations(db: Session, user: User, limit: int = 30) -> List[Dict[str, Any]]:
    rows = db.scalars(select(AIConversation).where(AIConversation.user_id == user.id).order_by(AIConversation.updated_at.desc()).limit(limit)).all()
    return [{"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat(), "message_count": len(c.messages)} for c in rows]


def get_conversation(db: Session, user: User, conv_id: uuid.UUID) -> Dict[str, Any]:
    conv = db.get(AIConversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise NotFoundError("Conversation not found")
    msgs = []
    for m in conv.messages:
        msgs.append({"id": str(m.id), "role": m.role, "content": m.content, "confidence": m.confidence, "evidence_sufficient": m.evidence_sufficient, "limitations": m.limitations, "provider": m.provider, "recommendation_id": str(m.recommendation_id) if m.recommendation_id else None, "created_at": m.created_at.isoformat(), "citations": [{"marker": c.marker, "document_id": str(c.document_id) if c.document_id else None, "page": c.page, "excerpt": c.excerpt, "score": c.score} for c in m.citations]})
    return {"id": str(conv.id), "title": conv.title, "messages": msgs}
