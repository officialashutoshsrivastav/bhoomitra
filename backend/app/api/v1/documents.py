from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, get_permissions, load_user_permissions, require_permissions
from app.core.config import settings
from app.core.permissions import P
from app.db.database import get_db
from app.ingestion import pipeline
from app.models.identity import Organization, User
from app.models.knowledge import DocumentVersion, Visibility
from app.schemas.common import Message, Page, PageParams
from app.schemas.knowledge import ChunkOut, DocumentCreate, DocumentDetail, DocumentOut, DocumentUpdate, DocumentVersionOut, RelationCreate, ReviewDecision
from app.services import document_service as svc
from app.storage.service import read_upload

router = APIRouter(prefix="/documents", tags=["documents"])


def _perms_for(request: Request, user: Optional[User], db: Session) -> set:
    if user is None:
        return set()
    return getattr(request.state, "permissions", None) or load_user_permissions(db, user)


def _job_info(job) -> Optional[dict]:
    if not job:
        return None
    return {"id": str(job.id), "status": job.status, "progress": job.progress, "error": job.error, "retry_count": job.retry_count, "started_at": job.started_at.isoformat() if job.started_at else None, "completed_at": job.completed_at.isoformat() if job.completed_at else None}


def _detail(db: Session, doc, user, perms) -> DocumentDetail:
    out = DocumentDetail(**DocumentOut.model_validate(doc).model_dump())
    out.versions = [DocumentVersionOut.model_validate(v) for v in doc.versions]
    if doc.organization_id:
        out.organization_name = db.scalar(select(Organization.name).where(Organization.id == doc.organization_id))
    out.related = svc.related_documents(db, doc, user, perms)
    out.reviews = [{"id": str(r.id), "reviewer_id": str(r.reviewer_id), "decision": r.decision, "comments": r.comments, "created_at": r.created_at.isoformat()} for r in doc.reviews]
    if doc.current_version_id:
        out.processing_job = _job_info(pipeline.latest_job_for_version(db, doc.current_version_id))
    return out


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    request: Request,
    page: PageParams = Depends(),
    q: Annotated[Optional[str], Query(max_length=200)] = None,
    document_type: Optional[str] = None,
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    topic: Optional[str] = None,
    policy_area: Optional[str] = None,
    geography: Optional[str] = None,
    organization_id: Optional[uuid.UUID] = None,
    year: Annotated[Optional[int], Query(ge=1900, le=2100)] = None,
    language: Optional[str] = None,
    mine: bool = False,
    include_demo: bool = True,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    perms = _perms_for(request, user, db)
    rows, total = svc.list_documents(db, user, perms, q=q, document_type=document_type, status=status_filter, topic=topic, policy_area=policy_area, geography=geography, organization_id=organization_id, year=year, language=language, mine=mine, include_demo=include_demo, offset=page.offset, limit=page.page_size, sort=page.sort)
    return Page.build([DocumentOut.model_validate(d) for d in rows], total, page.page, page.page_size)


@router.get("/pending-review", response_model=Page[DocumentOut])
def pending_review(page: PageParams = Depends(), user: User = Depends(require_permissions(P.DOCUMENT_REVIEW)), db: Session = Depends(get_db)):
    rows, total = svc.pending_review(db, page.offset, page.page_size)
    return Page.build([DocumentOut.model_validate(d) for d in rows], total, page.page, page.page_size)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, request: Request, user: User = Depends(require_permissions(P.DOCUMENT_CREATE)), db: Session = Depends(get_db)):
    return DocumentOut.model_validate(svc.create_document(db, payload, user, request))


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: uuid.UUID, request: Request, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    perms = _perms_for(request, user, db)
    doc = svc.get_document(db, doc_id, user, perms)
    doc.view_count = (doc.view_count or 0) + 1
    db.commit()
    return _detail(db, doc, user, perms)


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: uuid.UUID, payload: DocumentUpdate, request: Request, user: User = Depends(require_permissions(P.DOCUMENT_UPDATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.update_document(db, doc, payload, user, perms, request))


@router.post("/{doc_id}/versions", response_model=DocumentVersionOut, status_code=status.HTTP_201_CREATED)
async def upload_version(doc_id: uuid.UUID, request: Request, file: UploadFile = File(...), change_note: Optional[str] = Form(None), version_label: Optional[str] = Form(None), user: User = Depends(require_permissions(P.DOCUMENT_CREATE, P.DOCUMENT_UPDATE, any_of=True)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    data = read_upload(file.file, settings.max_upload_mb)
    version, job = svc.upload_version(db, doc, data=data, filename=file.filename or "upload", declared_mime=file.content_type, user=user, perms=perms, change_note=change_note, version_label=version_label, request=request)
    return DocumentVersionOut.model_validate(version)


@router.get("/{doc_id}/versions", response_model=List[DocumentVersionOut])
def list_versions(doc_id: uuid.UUID, request: Request, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, _perms_for(request, user, db))
    return [DocumentVersionOut.model_validate(v) for v in doc.versions]


@router.get("/{doc_id}/versions/{version_id}/status")
def version_status(doc_id: uuid.UUID, version_id: uuid.UUID, request: Request, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, _perms_for(request, user, db))
    v = db.get(DocumentVersion, version_id)
    if not v or v.document_id != doc.id:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Version not found")
    return {"version_id": str(v.id), "processing_status": v.processing_status.value, "processing_error": v.processing_error, "attempts": v.processing_attempts, "ocr_applied": v.ocr_applied, "chunks": len(v.chunks), "job": _job_info(pipeline.latest_job_for_version(db, v.id))}


@router.post("/{doc_id}/versions/{version_id}/retry", response_model=Message)
def retry_version(doc_id: uuid.UUID, version_id: uuid.UUID, user: User = Depends(require_permissions(P.DOCUMENT_UPDATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    v = db.get(DocumentVersion, version_id)
    if not v or v.document_id != doc.id:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Version not found")
    job = pipeline.retry_processing(db, v, user.id)
    return Message(message="Processing re-queued", detail={"job_id": str(job.id)})


@router.post("/{doc_id}/versions/{version_id}/set-current", response_model=DocumentOut)
def set_current(doc_id: uuid.UUID, version_id: uuid.UUID, user: User = Depends(require_permissions(P.DOCUMENT_UPDATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.set_current_version(db, doc, version_id, user, perms))


@router.get("/{doc_id}/download")
def download(doc_id: uuid.UUID, request: Request, version_id: Optional[uuid.UUID] = None, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, _perms_for(request, user, db))
    v, stream = svc.download(db, doc, version_id, user, request)
    headers = {"Content-Disposition": f'attachment; filename="{v.file_name}"', "Content-Length": str(v.file_size), "X-Checksum-SHA256": v.checksum_sha256}
    return StreamingResponse(stream, media_type=v.mime_type, headers=headers)


@router.get("/{doc_id}/chunks", response_model=Page[ChunkOut])
def list_chunks(doc_id: uuid.UUID, request: Request, page: PageParams = Depends(), user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, _perms_for(request, user, db))
    rows, total = svc.chunks(db, doc, page.page_size, page.offset)
    return Page.build([ChunkOut(id=c.id, chunk_index=c.chunk_index, page_start=c.page_start, page_end=c.page_end, content=c.content) for c in rows], total, page.page, page.page_size)


@router.post("/{doc_id}/submit", response_model=DocumentOut)
def submit(doc_id: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.DOCUMENT_CREATE, P.DOCUMENT_UPDATE, any_of=True)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.submit_for_review(db, doc, user, perms, request))


@router.post("/{doc_id}/review", response_model=DocumentOut)
def review(doc_id: uuid.UUID, payload: ReviewDecision, request: Request, user: User = Depends(require_permissions(P.DOCUMENT_REVIEW)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.review(db, doc, payload.decision, payload.comments, user, request))


@router.post("/{doc_id}/publish", response_model=DocumentOut)
def publish(doc_id: uuid.UUID, request: Request, visibility: Optional[Visibility] = None, user: User = Depends(require_permissions(P.DOCUMENT_PUBLISH)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.publish(db, doc, user, visibility, request))


@router.post("/{doc_id}/archive", response_model=DocumentOut)
def archive(doc_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    return DocumentOut.model_validate(svc.archive(db, doc, user, perms, request))


@router.delete("/{doc_id}", response_model=Message)
def delete_document(doc_id: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.DOCUMENT_DELETE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    svc.soft_delete(db, doc, user, request)
    return Message(message="Document deleted")


@router.post("/{doc_id}/relations", response_model=Message, status_code=status.HTTP_201_CREATED)
def add_relation(doc_id: uuid.UUID, payload: RelationCreate, user: User = Depends(require_permissions(P.DOCUMENT_UPDATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id, user, perms)
    svc.add_relation(db, doc, payload.related_document_id, payload.relation_type, user, perms)
    return Message(message="Relation added")
