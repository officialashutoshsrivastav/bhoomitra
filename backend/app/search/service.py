from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import Float, String, and_, cast, desc, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedding_provider
from app.core.config import settings
from app.models.datasets import Dataset, DatasetStatus
from app.models.identity import Organization, User
from app.models.knowledge import Document, DocumentChunk, DocumentStatus, Policy, ResearchProject, Visibility
from app.models.platform import Challenge, ChallengeStatus, SavedSearch, SearchHistory
from app.search import opensearch_client as os_client

ENTITY_TYPES = ("document", "dataset", "policy", "research_project", "challenge")


@dataclass
class SearchFilters:
    entity_types: Optional[List[str]] = None
    topic: Optional[str] = None
    geography: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    document_type: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None
    policy_area: Optional[str] = None
    research_area: Optional[str] = None
    language: Optional[str] = None
    source: Optional[str] = None
    include_demo: bool = True


@dataclass
class SearchHit:
    entity_type: str
    entity_id: str
    title: str
    snippet: Optional[str]
    score: float
    keyword_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    keyword_score: Optional[float] = None
    vector_score: Optional[float] = None
    matched_by: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False


def _visibility_clause(user: Optional[User], perms: Set[str]):
    """Public users only see published/public content. Authenticated users with
    document.read see internal too; restricted/private need explicit rights."""
    if user is None:
        return and_(Document.status == DocumentStatus.PUBLISHED, Document.visibility == Visibility.PUBLIC)
    allowed = [Visibility.PUBLIC, Visibility.INTERNAL]
    if "document.review" in perms or "document.publish" in perms or user.is_superuser:
        allowed.extend([Visibility.RESTRICTED, Visibility.PRIVATE])
        return Document.visibility.in_(allowed)
    return and_(Document.visibility.in_(allowed), or_(Document.status.in_([DocumentStatus.PUBLISHED, DocumentStatus.APPROVED]), Document.created_by == user.id))


def _apply_document_filters(stmt, f: SearchFilters):
    if f.topic:
        stmt = stmt.where(Document.topic.ilike(f"%{f.topic}%"))
    if f.geography:
        stmt = stmt.where(Document.geography.ilike(f"%{f.geography}%"))
    if f.document_type:
        stmt = stmt.where(Document.document_type == f.document_type)
    if f.organization_id:
        stmt = stmt.where(Document.organization_id == f.organization_id)
    if f.policy_area:
        stmt = stmt.where(Document.policy_area.ilike(f"%{f.policy_area}%"))
    if f.research_area:
        stmt = stmt.where(Document.research_area.ilike(f"%{f.research_area}%"))
    if f.language:
        stmt = stmt.where(Document.language == f.language)
    if f.source:
        stmt = stmt.where(Document.source.ilike(f"%{f.source}%"))
    if f.date_from:
        stmt = stmt.where(Document.publication_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Document.publication_date <= f.date_to)
    if not f.include_demo:
        stmt = stmt.where(Document.is_demo.is_(False))
    return stmt.where(Document.deleted_at.is_(None))


# ---------------------------------------------------------------------------
# Keyword retrieval (PostgreSQL full-text search fallback)
# ---------------------------------------------------------------------------
def _fts_query(q: str):
    return func.websearch_to_tsquery("english", q)


def keyword_documents(db: Session, q: str, f: SearchFilters, user: Optional[User], perms: Set[str], limit: int) -> List[SearchHit]:
    """Metadata-level FTS (title/keywords/description/abstract, weighted) unioned
    with body-level FTS over the current version's chunks (best chunk per doc)."""
    tsq = _fts_query(q)
    rank = func.ts_rank_cd(Document.search_vector, tsq)
    stmt = select(Document, rank.label("rank")).where(Document.search_vector.op("@@")(tsq), _visibility_clause(user, perms))
    stmt = _apply_document_filters(stmt, f).order_by(desc("rank")).limit(limit)
    hits: List[SearchHit] = []
    seen: Dict[str, SearchHit] = {}
    for doc, r in db.execute(stmt).all():
        h = SearchHit(entity_type="document", entity_id=str(doc.id), title=doc.title, snippet=(doc.description or doc.abstract or "")[:240], score=float(r or 0) + 1.0, keyword_score=float(r or 0) + 1.0, matched_by=["keyword"], is_demo=doc.is_demo, metadata={"document_type": doc.document_type.value, "publication_date": doc.publication_date.isoformat() if doc.publication_date else None, "topic": doc.topic, "geography": doc.geography, "status": doc.status.value})
        seen[h.entity_id] = h
        hits.append(h)
    # body-level match via chunks
    crank = func.max(func.ts_rank_cd(DocumentChunk.search_vector, tsq)).label("crank")
    headline = func.max(func.ts_headline("english", DocumentChunk.content, tsq, "MaxWords=35, MinWords=15, MaxFragments=1"))
    cstmt = (
        select(Document, crank, headline)
        .join(DocumentChunk, and_(DocumentChunk.document_id == Document.id, DocumentChunk.version_id == Document.current_version_id))
        .where(DocumentChunk.search_vector.op("@@")(tsq), _visibility_clause(user, perms))
    )
    cstmt = _apply_document_filters(cstmt, f).group_by(Document.id).order_by(desc("crank")).limit(limit)
    for doc, r, snippet in db.execute(cstmt).all():
        key = str(doc.id)
        if key in seen:
            seen[key].keyword_score = (seen[key].keyword_score or 0) + float(r or 0)
            seen[key].score = seen[key].keyword_score
            if snippet:
                seen[key].snippet = snippet
            continue
        h = SearchHit(entity_type="document", entity_id=key, title=doc.title, snippet=snippet or (doc.description or "")[:240], score=float(r or 0), keyword_score=float(r or 0), matched_by=["keyword"], is_demo=doc.is_demo, metadata={"document_type": doc.document_type.value, "publication_date": doc.publication_date.isoformat() if doc.publication_date else None, "topic": doc.topic, "geography": doc.geography, "status": doc.status.value})
        seen[key] = h
        hits.append(h)
    hits.sort(key=lambda h: -(h.keyword_score or 0))
    # trigram title fallback for short/misspelt queries
    if len(hits) < 3 and len(q) >= 3:
        sim = func.similarity(Document.title, q)
        stmt2 = select(Document, sim.label("rank")).where(sim > 0.15, _visibility_clause(user, perms))
        stmt2 = _apply_document_filters(stmt2, f).order_by(desc("rank")).limit(limit)
        seen = {h.entity_id for h in hits}
        for doc, r in db.execute(stmt2).all():
            if str(doc.id) in seen:
                continue
            hits.append(SearchHit(entity_type="document", entity_id=str(doc.id), title=doc.title, snippet=(doc.description or "")[:240], score=float(r or 0), keyword_score=float(r or 0), matched_by=["fuzzy_title"], is_demo=doc.is_demo, metadata={"document_type": doc.document_type.value, "status": doc.status.value}))
    return hits


def keyword_other_entities(db: Session, q: str, f: SearchFilters, user: Optional[User], types: Sequence[str], limit: int) -> List[SearchHit]:
    hits: List[SearchHit] = []
    like = f"%{q}%"
    if "dataset" in types:
        stmt = select(Dataset).where(Dataset.deleted_at.is_(None), or_(Dataset.name.ilike(like), Dataset.description.ilike(like), func.array_to_string(Dataset.keywords, " ").ilike(like)))
        if user is None:
            stmt = stmt.where(Dataset.status == DatasetStatus.PUBLISHED, Dataset.access_level.in_(["public", "open"]))
        if f.geography:
            stmt = stmt.where(Dataset.geography.ilike(f"%{f.geography}%"))
        if f.topic:
            stmt = stmt.where(cast(Dataset.category, String).ilike(f"%{f.topic}%"))
        if f.organization_id:
            stmt = stmt.where(Dataset.organization_id == f.organization_id)
        if not f.include_demo:
            stmt = stmt.where(Dataset.is_demo.is_(False))
        for ds in db.scalars(stmt.limit(limit)).all():
            score = 1.0 if q.lower() in ds.name.lower() else 0.5
            hits.append(SearchHit(entity_type="dataset", entity_id=str(ds.id), title=ds.name, snippet=(ds.description or "")[:240], score=score, keyword_score=score, matched_by=["keyword"], is_demo=ds.is_demo, metadata={"category": ds.category.value, "format": ds.format, "geography": ds.geography, "status": ds.status.value}))
    if "policy" in types:
        stmt = select(Policy).where(Policy.deleted_at.is_(None), or_(Policy.title.ilike(like), Policy.summary.ilike(like)))
        if f.policy_area:
            stmt = stmt.where(Policy.policy_area.ilike(f"%{f.policy_area}%"))
        if not f.include_demo:
            stmt = stmt.where(Policy.is_demo.is_(False))
        for p in db.scalars(stmt.limit(limit)).all():
            score = 1.0 if q.lower() in p.title.lower() else 0.5
            hits.append(SearchHit(entity_type="policy", entity_id=str(p.id), title=p.title, snippet=(p.summary or "")[:240], score=score, keyword_score=score, matched_by=["keyword"], is_demo=p.is_demo, metadata={"policy_area": p.policy_area, "level": p.level, "status": p.status.value}))
    if "research_project" in types and user is not None:
        stmt = select(ResearchProject).where(ResearchProject.deleted_at.is_(None), or_(ResearchProject.title.ilike(like), ResearchProject.summary.ilike(like)))
        if f.research_area:
            stmt = stmt.where(ResearchProject.research_area.ilike(f"%{f.research_area}%"))
        for r in db.scalars(stmt.limit(limit)).all():
            score = 1.0 if q.lower() in r.title.lower() else 0.5
            hits.append(SearchHit(entity_type="research_project", entity_id=str(r.id), title=r.title, snippet=(r.summary or "")[:240], score=score, keyword_score=score, matched_by=["keyword"], is_demo=r.is_demo, metadata={"research_area": r.research_area, "status": r.status.value}))
    if "challenge" in types:
        stmt = select(Challenge).where(Challenge.deleted_at.is_(None), or_(Challenge.title.ilike(like), Challenge.summary.ilike(like)))
        if user is None:
            stmt = stmt.where(Challenge.status.in_([ChallengeStatus.PUBLISHED, ChallengeStatus.OPEN, ChallengeStatus.EVALUATION, ChallengeStatus.SHORTLISTED, ChallengeStatus.PILOT, ChallengeStatus.COMPLETED]))
        for c in db.scalars(stmt.limit(limit)).all():
            score = 1.0 if q.lower() in c.title.lower() else 0.5
            hits.append(SearchHit(entity_type="challenge", entity_id=str(c.id), title=c.title, snippet=(c.summary or "")[:240], score=score, keyword_score=score, matched_by=["keyword"], is_demo=c.is_demo, metadata={"challenge_type": c.challenge_type, "status": c.status.value}))
    return hits


# ---------------------------------------------------------------------------
# Vector retrieval (pgvector, cosine)
# ---------------------------------------------------------------------------
def vector_chunks(db: Session, q: str, f: SearchFilters, user: Optional[User], perms: Set[str], limit: int, document_ids: Optional[List[uuid.UUID]] = None) -> List[Tuple[DocumentChunk, Document, float]]:
    provider = get_embedding_provider()
    qvec = provider.embed_one(q)
    distance = DocumentChunk.embedding.cosine_distance(qvec)
    stmt = (
        select(DocumentChunk, Document, (1 - distance).label("sim"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.embedding.is_not(None), DocumentChunk.version_id == Document.current_version_id, _visibility_clause(user, perms))
    )
    stmt = _apply_document_filters(stmt, f)
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))
    stmt = stmt.order_by(distance).limit(limit)
    db.execute(text(f"SET LOCAL hnsw.ef_search = {max(40, limit * 2)}"))
    return [(c, d, float(s)) for c, d, s in db.execute(stmt).all()]


def vector_documents(db: Session, q: str, f: SearchFilters, user: Optional[User], perms: Set[str], limit: int) -> List[SearchHit]:
    rows = vector_chunks(db, q, f, user, perms, limit * 3)
    best: Dict[str, SearchHit] = {}
    for chunk, doc, sim in rows:
        key = str(doc.id)
        if key in best and best[key].vector_score >= sim:
            continue
        best[key] = SearchHit(entity_type="document", entity_id=key, title=doc.title, snippet=chunk.content[:240], score=sim, vector_score=sim, matched_by=["semantic"], is_demo=doc.is_demo, metadata={"document_type": doc.document_type.value, "page": chunk.page_start, "chunk_id": str(chunk.id), "status": doc.status.value})
    return sorted(best.values(), key=lambda h: -h.score)[:limit]


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(*ranked_lists: List[SearchHit], k: int = 60) -> List[SearchHit]:
    fused: Dict[str, SearchHit] = {}
    for lst in ranked_lists:
        for rank, hit in enumerate(lst, start=1):
            key = f"{hit.entity_type}:{hit.entity_id}"
            contribution = 1.0 / (k + rank)
            if key in fused:
                cur = fused[key]
                cur.score += contribution
                cur.matched_by = sorted(set(cur.matched_by) | set(hit.matched_by))
                cur.keyword_score = cur.keyword_score if cur.keyword_score is not None else hit.keyword_score
                cur.vector_score = cur.vector_score if cur.vector_score is not None else hit.vector_score
                cur.keyword_rank = cur.keyword_rank if cur.keyword_rank is not None else hit.keyword_rank
                cur.vector_rank = cur.vector_rank if cur.vector_rank is not None else hit.vector_rank
                if not cur.snippet and hit.snippet:
                    cur.snippet = hit.snippet
                cur.metadata = {**hit.metadata, **cur.metadata}
            else:
                hit.score = contribution
                if "keyword" in hit.matched_by or "fuzzy_title" in hit.matched_by:
                    hit.keyword_rank = rank
                if "semantic" in hit.matched_by:
                    hit.vector_rank = rank
                fused[key] = hit
    return sorted(fused.values(), key=lambda h: -h.score)


def hybrid_search(db: Session, q: str, f: SearchFilters, user: Optional[User], perms: Set[str], page: int, page_size: int, sort: str = "relevance") -> Tuple[List[SearchHit], int, Dict[str, Any]]:
    q = (q or "").strip()
    types = f.entity_types or list(ENTITY_TYPES)
    info: Dict[str, Any] = {"keyword_backend": "postgres_fts", "vector_backend": "pgvector", "fusion": "rrf", "embedding_model": get_embedding_provider().model_name}
    keyword_hits: List[SearchHit] = []
    vector_hits: List[SearchHit] = []
    if q:
        os_hits = os_client.keyword_search(q, {"document_type": f.document_type, "language": f.language, "date_from": f.date_from, "date_to": f.date_to}, size=60) if "document" in types else None
        if os_hits is not None:
            info["keyword_backend"] = "opensearch"
            allowed_docs = _load_allowed_documents(db, [h["entity_id"] for h in os_hits if h["entity_type"] == "document"], user, perms, f)
            for h in os_hits:
                if h["entity_type"] == "document" and h["entity_id"] in allowed_docs:
                    d = allowed_docs[h["entity_id"]]
                    keyword_hits.append(SearchHit(entity_type="document", entity_id=str(d.id), title=d.title, snippet=h.get("snippet") or (d.description or "")[:240], score=h["score"], keyword_score=h["score"], matched_by=["keyword"], is_demo=d.is_demo, metadata={"document_type": d.document_type.value, "status": d.status.value}))
        elif "document" in types:
            keyword_hits.extend(keyword_documents(db, q, f, user, perms, 60))
        keyword_hits.extend(keyword_other_entities(db, q, f, user, [t for t in types if t != "document"], 30))
        if "document" in types:
            try:
                vector_hits = vector_documents(db, q, f, user, perms, 40)
            except Exception as exc:  # pragma: no cover
                info["vector_error"] = str(exc)[:120]
        fused = reciprocal_rank_fusion(keyword_hits, vector_hits)
    else:
        fused = browse_recent(db, f, user, perms, types)
        info["mode"] = "browse"
    if sort == "date":
        fused.sort(key=lambda h: h.metadata.get("publication_date") or "", reverse=True)
    elif sort == "title":
        fused.sort(key=lambda h: h.title.lower())
    total = len(fused)
    start = (page - 1) * page_size
    return fused[start : start + page_size], total, info


def _load_allowed_documents(db: Session, ids: List[str], user: Optional[User], perms: Set[str], f: SearchFilters) -> Dict[str, Document]:
    if not ids:
        return {}
    uuids = [uuid.UUID(i) for i in ids if _is_uuid(i)]
    stmt = select(Document).where(Document.id.in_(uuids), _visibility_clause(user, perms))
    stmt = _apply_document_filters(stmt, f)
    return {str(d.id): d for d in db.scalars(stmt).all()}


def _is_uuid(v: str) -> bool:
    try:
        uuid.UUID(v)
        return True
    except ValueError:
        return False


def browse_recent(db: Session, f: SearchFilters, user: Optional[User], perms: Set[str], types: Sequence[str]) -> List[SearchHit]:
    hits: List[SearchHit] = []
    if "document" in types:
        stmt = _apply_document_filters(select(Document).where(_visibility_clause(user, perms)), f).order_by(Document.publication_date.desc().nullslast(), Document.created_at.desc()).limit(60)
        for doc in db.scalars(stmt).all():
            hits.append(SearchHit(entity_type="document", entity_id=str(doc.id), title=doc.title, snippet=(doc.description or "")[:240], score=0.0, matched_by=["browse"], is_demo=doc.is_demo, metadata={"document_type": doc.document_type.value, "publication_date": doc.publication_date.isoformat() if doc.publication_date else None, "topic": doc.topic, "geography": doc.geography, "status": doc.status.value}))
    return hits


# ---------------------------------------------------------------------------
# Autocomplete, saved & recent searches, facets
# ---------------------------------------------------------------------------
def autocomplete(db: Session, prefix: str, user: Optional[User], perms: Set[str], limit: int = 8) -> List[Dict[str, str]]:
    prefix = prefix.strip()
    if len(prefix) < 2:
        return []
    out: List[Dict[str, str]] = []
    os_sugg = os_client.suggest(prefix, limit)
    if os_sugg:
        out.extend({"label": s, "type": "document"} for s in os_sugg)
    if len(out) < limit:
        sim = func.similarity(Document.title, prefix)
        stmt = select(Document.title).where(or_(Document.title.ilike(f"{prefix}%"), Document.title.ilike(f"% {prefix}%"), sim > 0.3), _visibility_clause(user, perms), Document.deleted_at.is_(None)).order_by(desc(sim)).limit(limit)
        out.extend({"label": t, "type": "document"} for t in db.scalars(stmt).all())
        stmt = select(Dataset.name).where(Dataset.name.ilike(f"%{prefix}%"), Dataset.deleted_at.is_(None)).limit(4)
        out.extend({"label": t, "type": "dataset"} for t in db.scalars(stmt).all())
        stmt = select(Policy.title).where(Policy.title.ilike(f"%{prefix}%"), Policy.deleted_at.is_(None)).limit(3)
        out.extend({"label": t, "type": "policy"} for t in db.scalars(stmt).all())
    seen, dedup = set(), []
    for o in out:
        if o["label"] not in seen:
            seen.add(o["label"])
            dedup.append(o)
    return dedup[:limit]


def record_history(db: Session, user: Optional[User], q: str, filters: Dict[str, Any], count: int) -> None:
    if not q:
        return
    db.add(SearchHistory(user_id=user.id if user else None, query=q[:500], filters=filters, result_count=count))
    db.commit()


def recent_searches(db: Session, user: User, limit: int = 10) -> List[Dict[str, Any]]:
    stmt = select(SearchHistory.query, func.max(SearchHistory.created_at).label("last"), func.max(SearchHistory.result_count)).where(SearchHistory.user_id == user.id).group_by(SearchHistory.query).order_by(desc("last")).limit(limit)
    return [{"query": q, "last_used": last.isoformat(), "result_count": c} for q, last, c in db.execute(stmt).all()]


def facets(db: Session, user: Optional[User], perms: Set[str]) -> Dict[str, List[Dict[str, Any]]]:
    base = select(Document).where(_visibility_clause(user, perms), Document.deleted_at.is_(None)).subquery()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for name, col in (("document_type", base.c.document_type), ("topic", base.c.topic), ("geography", base.c.geography), ("policy_area", base.c.policy_area), ("language", base.c.language), ("source", base.c.source)):
        rows = db.execute(select(col, func.count()).where(col.is_not(None)).group_by(col).order_by(func.count().desc()).limit(15)).all()
        out[name] = [{"value": v, "count": c} for v, c in rows]
    years = db.execute(select(func.extract("year", base.c.publication_date).label("y"), func.count()).where(base.c.publication_date.is_not(None)).group_by("y").order_by(desc("y")).limit(12)).all()
    out["year"] = [{"value": str(int(y)), "count": c} for y, c in years]
    ds = db.execute(select(Dataset.category, func.count()).where(Dataset.deleted_at.is_(None)).group_by(Dataset.category).order_by(func.count().desc())).all()
    out["dataset_category"] = [{"value": c.value, "count": n} for c, n in ds]
    return out
