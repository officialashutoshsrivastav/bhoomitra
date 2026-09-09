from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.datasets import Dataset
from app.models.identity import Organization
from app.models.knowledge import Document, DocumentChunk, Policy, ResearchProject
from app.models.platform import Challenge
from app.search import opensearch_client as os_client


def _org_name(db: Session, org_id: Optional[uuid.UUID]) -> Optional[str]:
    if not org_id:
        return None
    return db.scalar(select(Organization.name).where(Organization.id == org_id))


def document_payload(db: Session, doc: Document) -> Dict[str, Any]:
    body_parts = [doc.description or "", doc.abstract or ""]
    if doc.current_version_id:
        chunks = db.scalars(select(DocumentChunk.content).where(DocumentChunk.version_id == doc.current_version_id).order_by(DocumentChunk.chunk_index).limit(40)).all()
        body_parts.extend(chunks)
    return {
        "entity_type": "document",
        "entity_id": str(doc.id),
        "title": doc.title,
        "body": "\n".join(p for p in body_parts if p)[:200000],
        "keywords": doc.keywords or [],
        "topic": doc.topic,
        "policy_area": doc.policy_area,
        "research_area": doc.research_area,
        "document_type": doc.document_type.value,
        "organization": _org_name(db, doc.organization_id),
        "geography": doc.geography,
        "language": doc.language,
        "source": doc.source,
        "status": doc.status.value,
        "visibility": doc.visibility.value,
        "published_at": doc.publication_date.isoformat() if doc.publication_date else None,
        "is_demo": doc.is_demo,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def dataset_payload(db: Session, ds: Dataset) -> Dict[str, Any]:
    return {
        "entity_type": "dataset",
        "entity_id": str(ds.id),
        "title": ds.name,
        "body": "\n".join(p for p in [ds.description or "", ds.provenance or "", ds.quality_notes or ""] if p),
        "keywords": ds.keywords or [],
        "topic": ds.category.value,
        "organization": _org_name(db, ds.organization_id),
        "geography": ds.geography,
        "source": ds.publisher,
        "status": ds.status.value,
        "visibility": ds.access_level,
        "published_at": ds.temporal_end.isoformat() if ds.temporal_end else None,
        "is_demo": ds.is_demo,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
    }


def policy_payload(db: Session, p: Policy) -> Dict[str, Any]:
    return {"entity_type": "policy", "entity_id": str(p.id), "title": p.title, "body": p.summary or "", "keywords": [], "policy_area": p.policy_area, "geography": p.geography, "status": p.status.value, "source": p.ministry, "published_at": p.effective_date.isoformat() if p.effective_date else None, "is_demo": p.is_demo, "updated_at": p.updated_at.isoformat() if p.updated_at else None}


def research_payload(db: Session, r: ResearchProject) -> Dict[str, Any]:
    return {"entity_type": "research_project", "entity_id": str(r.id), "title": r.title, "body": r.summary or "", "keywords": r.keywords or [], "research_area": r.research_area, "geography": r.geography, "organization": _org_name(db, r.organization_id), "status": r.status.value, "is_demo": r.is_demo, "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def challenge_payload(db: Session, c: Challenge) -> Dict[str, Any]:
    return {"entity_type": "challenge", "entity_id": str(c.id), "title": c.title, "body": "\n".join(p for p in [c.summary or "", c.description or ""] if p), "keywords": [], "topic": c.theme, "organization": _org_name(db, c.organization_id), "status": c.status.value, "is_demo": c.is_demo, "updated_at": c.updated_at.isoformat() if c.updated_at else None}


def index_document(db: Session, doc: Document) -> bool:
    return os_client.index_document(document_payload(db, doc))


def index_dataset(db: Session, ds: Dataset) -> bool:
    return os_client.index_document(dataset_payload(db, ds))


def index_policy(db: Session, p: Policy) -> bool:
    return os_client.index_document(policy_payload(db, p))


def index_research(db: Session, r: ResearchProject) -> bool:
    return os_client.index_document(research_payload(db, r))


def index_challenge(db: Session, c: Challenge) -> bool:
    return os_client.index_document(challenge_payload(db, c))


def remove(entity_type: str, entity_id: uuid.UUID) -> bool:
    return os_client.delete_document(entity_type, str(entity_id))


def reindex_all(db: Session) -> Dict[str, int]:
    counts = {"document": 0, "dataset": 0, "policy": 0, "research_project": 0, "challenge": 0}
    for d in db.scalars(select(Document).where(Document.deleted_at.is_(None))).all():
        counts["document"] += int(index_document(db, d))
    for ds in db.scalars(select(Dataset).where(Dataset.deleted_at.is_(None))).all():
        counts["dataset"] += int(index_dataset(db, ds))
    for p in db.scalars(select(Policy).where(Policy.deleted_at.is_(None))).all():
        counts["policy"] += int(index_policy(db, p))
    for r in db.scalars(select(ResearchProject).where(ResearchProject.deleted_at.is_(None))).all():
        counts["research_project"] += int(index_research(db, r))
    for c in db.scalars(select(Challenge).where(Challenge.deleted_at.is_(None))).all():
        counts["challenge"] += int(index_challenge(db, c))
    return counts
