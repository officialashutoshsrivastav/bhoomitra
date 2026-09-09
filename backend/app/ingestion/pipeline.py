from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedding_provider
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.extract import chunk_pages, estimate_tokens, extract
from app.models.knowledge import Document, DocumentChunk, DocumentVersion, ProcessingStatus
from app.models.platform import BackgroundJob
from app.search import indexer
from app.storage.service import get_storage
from app.workers.dispatch import enqueue, register_job

logger = get_logger("bhoomitra.ingestion")


def _set_status(db: Session, version: DocumentVersion, status: ProcessingStatus, job: Optional[BackgroundJob] = None, progress: Optional[int] = None, error: Optional[str] = None) -> None:
    version.processing_status = status
    if error is not None:
        version.processing_error = error[:2000]
    if job is not None and progress is not None:
        job.progress = progress
    db.commit()


def process_version(db: Session, version_id: uuid.UUID, job: Optional[BackgroundJob] = None) -> Dict[str, Any]:
    """UPLOAD → VALIDATE → STORE(done) → EXTRACT METADATA → EXTRACT TEXT → OCR →
    CLEAN → CHUNK → EMBED → VECTOR INDEX → SEARCH INDEX → READY"""
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise ValueError(f"Document version {version_id} not found")
    document = db.get(Document, version.document_id)
    version.processing_attempts = (version.processing_attempts or 0) + 1
    storage = get_storage()

    _set_status(db, version, ProcessingStatus.VALIDATING, job, 5)
    if not storage.exists(version.storage_key):
        _set_status(db, version, ProcessingStatus.FAILED, job, error="Stored file is missing")
        raise FileNotFoundError(version.storage_key)
    data = storage.get(version.storage_key)
    from app.storage.service import sha256_bytes

    if sha256_bytes(data) != version.checksum_sha256:
        _set_status(db, version, ProcessingStatus.FAILED, job, error="Checksum mismatch — stored file differs from upload")
        raise ValueError("checksum mismatch")

    _set_status(db, version, ProcessingStatus.PROCESSING, job, 15)
    extraction = extract(data, version.mime_type)
    if extraction.ocr_applied:
        _set_status(db, version, ProcessingStatus.OCR_RUNNING, job, 35)
    version.ocr_applied = extraction.ocr_applied
    version.page_count = int(extraction.metadata.get("page_count") or len(extraction.pages))
    version.text_char_count = extraction.char_count
    version.extracted_metadata = {k: v for k, v in extraction.metadata.items()}
    version.language_detected = "en" if extraction.char_count else None
    db.commit()

    chunks = chunk_pages(extraction.pages)
    _set_status(db, version, ProcessingStatus.INDEXING, job, 55)
    db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
    provider = get_embedding_provider()
    texts = [c.content for c in chunks]
    embeddings = provider.embed(texts) if texts else []
    for c, emb in zip(chunks, embeddings):
        db.add(DocumentChunk(version_id=version.id, document_id=version.document_id, chunk_index=c.index, page_start=c.page_start, page_end=c.page_end, content=c.content, token_estimate=estimate_tokens(c.content), embedding=emb, embedding_model=provider.model_name))
    db.commit()
    if job:
        job.progress = 80
        db.commit()

    if document:
        indexer.index_document(db, document)
    version.processed_at = datetime.now(timezone.utc)
    version.processing_error = None
    _set_status(db, version, ProcessingStatus.READY, job, 100)
    logger.info("document processed", extra={"extra_data": {"version": str(version.id), "chunks": len(chunks), "ocr": extraction.ocr_applied, "chars": extraction.char_count}})
    return {"chunks": len(chunks), "chars": extraction.char_count, "ocr_applied": extraction.ocr_applied, "pages": version.page_count, "embedding_model": provider.model_name}


@register_job("document.process")
def _job_process_document(db: Session, job: BackgroundJob) -> Dict[str, Any]:
    vid = uuid.UUID(str(job.payload.get("version_id") or job.target_id))
    try:
        return process_version(db, vid, job)
    except Exception as exc:
        v = db.get(DocumentVersion, vid)
        if v is not None and v.processing_status != ProcessingStatus.FAILED:
            v.processing_status = ProcessingStatus.FAILED
            v.processing_error = str(exc)[:2000]
            db.commit()
        raise


def queue_processing(db: Session, version: DocumentVersion, user_id: Optional[uuid.UUID]) -> BackgroundJob:
    return enqueue(db, "document.process", target_type="document_version", target_id=version.id, payload={"version_id": str(version.id)}, created_by=user_id, max_retries=3)


def retry_processing(db: Session, version: DocumentVersion, user_id: Optional[uuid.UUID]) -> BackgroundJob:
    version.processing_status = ProcessingStatus.UPLOADED
    version.processing_error = None
    db.commit()
    return queue_processing(db, version, user_id)


def latest_job_for_version(db: Session, version_id: uuid.UUID) -> Optional[BackgroundJob]:
    return db.scalar(select(BackgroundJob).where(BackgroundJob.target_type == "document_version", BackgroundJob.target_id == version_id).order_by(BackgroundJob.created_at.desc()).limit(1))
