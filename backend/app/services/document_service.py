from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import service as audit
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import P
from app.ingestion import pipeline
from app.models.identity import Organization, User
from app.models.knowledge import Document, DocumentChunk, DocumentRelation, DocumentReview, DocumentStatus, DocumentVersion, ProcessingStatus, Visibility
from app.models.platform import Approval
from app.notifications.service import notify, notify_many
from app.schemas.knowledge import DocumentCreate, DocumentUpdate
from app.search import indexer
from app.storage.service import build_key, get_storage, sha256_bytes
from app.storage.validation import validate_upload
from app.models.identity import Permission, Role, RolePermission, UserRole

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 120) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")[:max_len].strip("-")
    return s or uuid.uuid4().hex[:12]


def unique_slug(db: Session, model, text: str) -> str:
    base = slugify(text)
    slug = base
    n = 1
    while db.scalar(select(model.id).where(model.slug == slug)):
        n += 1
        slug = f"{base[:110]}-{n}"
    return slug


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Access rules
# ---------------------------------------------------------------------------
def can_view(doc: Document, user: Optional[User], perms: Set[str]) -> bool:
    if doc.deleted_at is not None:
        return False
    if user is None:
        return doc.status == DocumentStatus.PUBLISHED and doc.visibility == Visibility.PUBLIC
    if user.is_superuser or doc.created_by == user.id:
        return True
    if doc.visibility in (Visibility.RESTRICTED, Visibility.PRIVATE):
        if P.DOCUMENT_REVIEW in perms or P.DOCUMENT_PUBLISH in perms:
            return True
        return doc.visibility == Visibility.RESTRICTED and doc.organization_id is not None and doc.organization_id == user.primary_organization_id and doc.status in (DocumentStatus.PUBLISHED, DocumentStatus.APPROVED)
    if doc.status in (DocumentStatus.PUBLISHED, DocumentStatus.APPROVED):
        return True
    return P.DOCUMENT_REVIEW in perms or P.DOCUMENT_PUBLISH in perms


def can_edit(doc: Document, user: User, perms: Set[str]) -> bool:
    if user.is_superuser or doc.created_by == user.id:
        return True
    return P.DOCUMENT_PUBLISH in perms or (P.DOCUMENT_UPDATE in perms and doc.organization_id is not None and doc.organization_id == user.primary_organization_id)


def get_document(db: Session, doc_id: uuid.UUID, user: Optional[User], perms: Set[str]) -> Document:
    doc = db.scalar(select(Document).options(selectinload(Document.versions), selectinload(Document.reviews), selectinload(Document.relations)).execution_options(populate_existing=True).where(Document.id == doc_id))
    if not doc or not can_view(doc, user, perms):
        raise NotFoundError("Document not found")
    return doc


# ---------------------------------------------------------------------------
# CRUD + upload
# ---------------------------------------------------------------------------
def create_document(db: Session, payload: DocumentCreate, user: User, request: Optional[Request] = None) -> Document:
    if payload.organization_id and not db.get(Organization, payload.organization_id):
        raise ValidationFailed("Organization not found")
    doc = Document(**payload.model_dump(), slug=unique_slug(db, Document, payload.title), created_by=user.id, status=DocumentStatus.DRAFT)
    db.add(doc)
    db.flush()
    audit.record(db, "document.create", user=user, resource_type="document", resource_id=doc.id, request=request)
    db.commit()
    db.refresh(doc)
    return doc


def update_document(db: Session, doc: Document, payload: DocumentUpdate, user: User, perms: Set[str], request: Optional[Request] = None) -> Document:
    if not can_edit(doc, user, perms):
        raise ForbiddenError("You cannot edit this document")
    if doc.status == DocumentStatus.PUBLISHED and P.DOCUMENT_PUBLISH not in perms and not user.is_superuser:
        raise ForbiddenError("Published documents can only be edited by publishers")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(doc, k, v)
    audit.record(db, "document.update", user=user, resource_type="document", resource_id=doc.id, detail={"fields": list(changes.keys())}, request=request)
    db.commit()
    indexer.index_document(db, doc)
    db.refresh(doc)
    return doc


def upload_version(db: Session, doc: Document, *, data: bytes, filename: str, declared_mime: Optional[str], user: User, perms: Set[str], change_note: Optional[str], version_label: Optional[str], request: Optional[Request] = None) -> Tuple[DocumentVersion, Any]:
    if not can_edit(doc, user, perms):
        raise ForbiddenError("You cannot upload versions for this document")
    mime = validate_upload(data, filename, declared_mime)
    checksum = sha256_bytes(data)
    dup = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.checksum_sha256 == checksum))
    if dup:
        raise ConflictError("An identical file is already attached to this document", details={"version_id": str(dup.id), "version_number": dup.version_number})
    next_no = (db.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == doc.id)) or 0) + 1
    key = build_key(f"documents/{doc.id}", filename)
    get_storage().put(key, data, mime)
    version = DocumentVersion(document_id=doc.id, version_number=next_no, version_label=version_label, change_note=change_note, file_name=filename[:500], storage_key=key, mime_type=mime, file_size=len(data), checksum_sha256=checksum, uploaded_by=user.id, processing_status=ProcessingStatus.UPLOADED)
    db.add(version)
    db.flush()
    doc.current_version_id = version.id
    audit.record(db, "document.upload_version", user=user, resource_type="document", resource_id=doc.id, detail={"version": next_no, "mime": mime, "size": len(data), "sha256": checksum}, request=request)
    db.commit()
    job = pipeline.queue_processing(db, version, user.id)
    db.refresh(version)
    return version, job


def set_current_version(db: Session, doc: Document, version_id: uuid.UUID, user: User, perms: Set[str]) -> Document:
    if not can_edit(doc, user, perms):
        raise ForbiddenError("You cannot change versions for this document")
    v = db.get(DocumentVersion, version_id)
    if not v or v.document_id != doc.id:
        raise NotFoundError("Version not found")
    doc.current_version_id = v.id
    audit.record(db, "document.set_current_version", user=user, resource_type="document", resource_id=doc.id, detail={"version": v.version_number})
    db.commit()
    indexer.index_document(db, doc)
    return doc


# ---------------------------------------------------------------------------
# Workflow: draft → in_review → approved → published → archived
# ---------------------------------------------------------------------------
def _reviewer_ids(db: Session) -> List[uuid.UUID]:
    stmt = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).join(RolePermission, RolePermission.role_id == Role.id).join(Permission, Permission.id == RolePermission.permission_id).where(Permission.code == P.DOCUMENT_REVIEW).distinct().limit(50)
    return list(db.scalars(stmt).all())


def submit_for_review(db: Session, doc: Document, user: User, perms: Set[str], request: Optional[Request] = None) -> Document:
    if not can_edit(doc, user, perms):
        raise ForbiddenError("You cannot submit this document")
    if doc.status not in (DocumentStatus.DRAFT, DocumentStatus.REJECTED):
        raise ConflictError(f"Document in status {doc.status.value} cannot be submitted")
    if not doc.current_version_id:
        raise ValidationFailed("Upload a file before submitting for review")
    doc.status = DocumentStatus.IN_REVIEW
    db.add(Approval(target_type="document", target_id=doc.id, title=f"Review document: {doc.title}", requested_by=user.id, status="pending"))
    notify_many(db, _reviewer_ids(db), "approval", "Document awaiting review", doc.title, link=f"/app/repository/{doc.id}")
    audit.record(db, "document.submit_review", user=user, resource_type="document", resource_id=doc.id, request=request)
    db.commit()
    return doc


def review(db: Session, doc: Document, decision: str, comments: Optional[str], reviewer: User, request: Optional[Request] = None) -> Document:
    if doc.status != DocumentStatus.IN_REVIEW:
        raise ConflictError("Document is not in review")
    db.add(DocumentReview(document_id=doc.id, reviewer_id=reviewer.id, decision=decision, comments=comments))
    approval = db.scalar(select(Approval).where(Approval.target_type == "document", Approval.target_id == doc.id, Approval.status == "pending").order_by(Approval.created_at.desc()))
    if decision == "approve":
        doc.status = DocumentStatus.APPROVED
        doc.approved_by = reviewer.id
        outcome = "approved"
    elif decision == "reject":
        doc.status = DocumentStatus.REJECTED
        outcome = "rejected"
    else:
        doc.status = DocumentStatus.DRAFT
        outcome = "changes_requested"
    if approval:
        approval.status = outcome
        approval.decided_by = reviewer.id
        approval.decided_at = _now()
        approval.decision_note = comments
    notify(db, doc.created_by, "review", f"Document {outcome.replace('_', ' ')}", f"{doc.title}: {comments or ''}".strip(), link=f"/app/repository/{doc.id}", email=True)
    audit.record(db, f"document.review.{outcome}", user=reviewer, resource_type="document", resource_id=doc.id, detail={"comments": comments}, request=request)
    db.commit()
    indexer.index_document(db, doc)
    return doc


def publish(db: Session, doc: Document, user: User, visibility: Optional[Visibility], request: Optional[Request] = None) -> Document:
    if doc.status not in (DocumentStatus.APPROVED, DocumentStatus.PUBLISHED):
        raise ConflictError("Only approved documents can be published")
    if not doc.current_version_id:
        raise ValidationFailed("Cannot publish a document without a file")
    doc.status = DocumentStatus.PUBLISHED
    doc.published_at = _now()
    if visibility:
        doc.visibility = visibility
    notify(db, doc.created_by, "publish", "Document published", doc.title, link=f"/app/repository/{doc.id}")
    audit.record(db, "document.publish", user=user, resource_type="document", resource_id=doc.id, request=request)
    db.commit()
    indexer.index_document(db, doc)
    return doc


def archive(db: Session, doc: Document, user: User, perms: Set[str], request: Optional[Request] = None) -> Document:
    if not (user.is_superuser or P.DOCUMENT_DELETE in perms or P.DOCUMENT_PUBLISH in perms or (doc.created_by == user.id and doc.status != DocumentStatus.PUBLISHED)):
        raise ForbiddenError("You cannot archive this document")
    doc.status = DocumentStatus.ARCHIVED
    audit.record(db, "document.archive", user=user, resource_type="document", resource_id=doc.id, request=request)
    db.commit()
    indexer.index_document(db, doc)
    return doc


def soft_delete(db: Session, doc: Document, user: User, request: Optional[Request] = None) -> None:
    doc.deleted_at = _now()
    audit.record(db, "document.delete", user=user, resource_type="document", resource_id=doc.id, request=request)
    db.commit()
    indexer.remove("document", doc.id)


# ---------------------------------------------------------------------------
# Relations, downloads, chunks
# ---------------------------------------------------------------------------
def add_relation(db: Session, doc: Document, related_id: uuid.UUID, relation_type: str, user: User, perms: Set[str]) -> None:
    if not can_edit(doc, user, perms):
        raise ForbiddenError("You cannot modify this document")
    if related_id == doc.id:
        raise ValidationFailed("A document cannot relate to itself")
    other = db.get(Document, related_id)
    if not other or not can_view(other, user, perms):
        raise NotFoundError("Related document not found")
    if db.get(DocumentRelation, {"document_id": doc.id, "related_document_id": related_id}):
        raise ConflictError("Relation already exists")
    db.add(DocumentRelation(document_id=doc.id, related_document_id=related_id, relation_type=relation_type))
    db.commit()


def related_documents(db: Session, doc: Document, user: Optional[User], perms: Set[str]) -> List[Dict[str, Any]]:
    ids = [r.related_document_id for r in doc.relations]
    if not ids:
        return []
    rows = db.scalars(select(Document).where(Document.id.in_(ids))).all()
    rel_types = {r.related_document_id: r.relation_type for r in doc.relations}
    return [{"id": str(d.id), "title": d.title, "document_type": d.document_type.value, "relation_type": rel_types.get(d.id, "related"), "is_demo": d.is_demo} for d in rows if can_view(d, user, perms)]


def download(db: Session, doc: Document, version_id: Optional[uuid.UUID], user: Optional[User], request: Optional[Request] = None) -> Tuple[DocumentVersion, Any]:
    vid = version_id or doc.current_version_id
    if not vid:
        raise NotFoundError("Document has no file")
    v = db.get(DocumentVersion, vid)
    if not v or v.document_id != doc.id:
        raise NotFoundError("Version not found")
    doc.download_count = (doc.download_count or 0) + 1
    audit.record(db, "document.download", user=user, resource_type="document", resource_id=doc.id, detail={"version": v.version_number}, request=request)
    db.commit()
    return v, get_storage().stream(v.storage_key)


def chunks(db: Session, doc: Document, limit: int, offset: int) -> Tuple[List[DocumentChunk], int]:
    if not doc.current_version_id:
        return [], 0
    total = db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.version_id == doc.current_version_id)) or 0
    rows = db.scalars(select(DocumentChunk).where(DocumentChunk.version_id == doc.current_version_id).order_by(DocumentChunk.chunk_index).offset(offset).limit(limit)).all()
    return rows, total


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def list_documents(db: Session, user: Optional[User], perms: Set[str], *, q: Optional[str], document_type: Optional[str], status: Optional[str], topic: Optional[str], policy_area: Optional[str], geography: Optional[str], organization_id: Optional[uuid.UUID], year: Optional[int], language: Optional[str], mine: bool, include_demo: bool, offset: int, limit: int, sort: Optional[str]) -> Tuple[List[Document], int]:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if user is None:
        stmt = stmt.where(Document.status == DocumentStatus.PUBLISHED, Document.visibility == Visibility.PUBLIC)
    else:
        allowed_vis = [Visibility.PUBLIC, Visibility.INTERNAL]
        privileged = user.is_superuser or P.DOCUMENT_REVIEW in perms or P.DOCUMENT_PUBLISH in perms
        if privileged:
            allowed_vis += [Visibility.RESTRICTED, Visibility.PRIVATE]
        vis_clause = Document.visibility.in_(allowed_vis)
        own = Document.created_by == user.id
        if privileged:
            stmt = stmt.where(or_(vis_clause, own))
        else:
            stmt = stmt.where(or_(own, (vis_clause & Document.status.in_([DocumentStatus.PUBLISHED, DocumentStatus.APPROVED])), (Document.visibility == Visibility.RESTRICTED) & (Document.organization_id == user.primary_organization_id) & Document.status.in_([DocumentStatus.PUBLISHED, DocumentStatus.APPROVED])))
        if mine:
            stmt = stmt.where(own)
    if q:
        tsq = func.websearch_to_tsquery("english", q)
        stmt = stmt.where(or_(Document.search_vector.op("@@")(tsq), Document.title.ilike(f"%{q}%")))
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if status:
        stmt = stmt.where(Document.status == status)
    if topic:
        stmt = stmt.where(Document.topic.ilike(f"%{topic}%"))
    if policy_area:
        stmt = stmt.where(Document.policy_area.ilike(f"%{policy_area}%"))
    if geography:
        stmt = stmt.where(Document.geography.ilike(f"%{geography}%"))
    if organization_id:
        stmt = stmt.where(Document.organization_id == organization_id)
    if year:
        stmt = stmt.where(func.extract("year", Document.publication_date) == year)
    if language:
        stmt = stmt.where(Document.language == language)
    if not include_demo:
        stmt = stmt.where(Document.is_demo.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = Document.publication_date.desc().nullslast()
    if sort:
        col = {"title": Document.title, "created_at": Document.created_at, "publication_date": Document.publication_date, "downloads": Document.download_count, "views": Document.view_count}.get(sort.lstrip("-"))
        if col is not None:
            order = col.desc().nullslast() if sort.startswith("-") else col.asc().nullsfirst()
    rows = db.scalars(stmt.order_by(order, Document.created_at.desc()).offset(offset).limit(limit)).all()
    return rows, total


def pending_review(db: Session, offset: int, limit: int) -> Tuple[List[Document], int]:
    stmt = select(Document).where(Document.status == DocumentStatus.IN_REVIEW, Document.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return db.scalars(stmt.order_by(Document.updated_at.asc()).offset(offset).limit(limit)).all(), total
