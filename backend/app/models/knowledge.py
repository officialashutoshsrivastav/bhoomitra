from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.database import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class DocumentType(str, enum.Enum):
    RESEARCH_PAPER = "research_paper"
    POLICY_PAPER = "policy_paper"
    GOVERNMENT_REPORT = "government_report"
    LEGAL_DOCUMENT = "legal_document"
    CASE_STUDY = "case_study"
    WORKING_PAPER = "working_paper"
    TECHNICAL_REPORT = "technical_report"
    GUIDELINE = "guideline"
    FRAMEWORK = "framework"
    PROJECT_REPORT = "project_report"
    POLICY_BRIEF = "policy_brief"
    SCHEME = "scheme"
    ACT_RULE = "act_rule"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Visibility(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    PRIVATE = "private"


class ProcessingStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PROCESSING = "PROCESSING"
    OCR_RUNNING = "OCR_RUNNING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


class Document(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_type_status", "document_type", "status"),
        Index("ix_documents_search", "search_vector", postgresql_using="gin"),
        Index("ix_documents_keywords", "keywords", postgresql_using="gin"),
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    authors: Mapped[List[str]] = mapped_column(ARRAY(String(255)), default=list, nullable=False)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255))
    publication_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, native_enum=False, length=40), nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    policy_area: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    research_area: Mapped[Optional[str]] = mapped_column(String(120))
    geography: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    keywords: Mapped[List[str]] = mapped_column(ARRAY(String(100)), default=list, nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(255))
    source_url: Mapped[Optional[str]] = mapped_column(String(1000))
    license: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, native_enum=False, length=20), default=DocumentStatus.DRAFT, nullable=False, index=True)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility, native_enum=False, length=20), default=Visibility.INTERNAL, nullable=False)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True, name="fk_documents_current_version"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)

    versions: Mapped[List["DocumentVersion"]] = relationship(back_populates="document", cascade="all, delete-orphan", foreign_keys="DocumentVersion.document_id", order_by="DocumentVersion.version_number")
    current_version: Mapped[Optional["DocumentVersion"]] = relationship(foreign_keys=[current_version_id], post_update=True)
    reviews: Mapped[List["DocumentReview"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    relations: Mapped[List["DocumentRelation"]] = relationship(back_populates="document", cascade="all, delete-orphan", foreign_keys="DocumentRelation.document_id")


class DocumentVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_version"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[Optional[str]] = mapped_column(String(50))
    change_note: Mapped[Optional[str]] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    text_char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language_detected: Mapped[Optional[str]] = mapped_column(String(20))
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, native_enum=False, length=20), default=ProcessingStatus.UPLOADED, nullable=False, index=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ocr_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extracted_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions", foreign_keys=[document_id])
    chunks: Mapped[List["DocumentChunk"]] = relationship(back_populates="version", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index")


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index", name="uq_chunk_version_index"),
        Index("ix_chunks_search", "search_vector", postgresql_using="gin"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.embedding_dim))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120))
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


class DocumentReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_reviews"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comments: Mapped[Optional[str]] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="reviews")


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    related_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(40), default="related", nullable=False)

    document: Mapped[Document] = relationship(back_populates="relations", foreign_keys=[document_id])


class ResearchStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    COMPLETED = "completed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ResearchProject(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "research_projects"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    research_area: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    geography: Mapped[Optional[str]] = mapped_column(String(255))
    lead_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    status: Mapped[ResearchStatus] = mapped_column(Enum(ResearchStatus, native_enum=False, length=20), default=ResearchStatus.PROPOSED, nullable=False, index=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    funding_source: Mapped[Optional[str]] = mapped_column(String(255))
    keywords: Mapped[List[str]] = mapped_column(ARRAY(String(100)), default=list, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    outputs: Mapped[List["ResearchOutput"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ResearchOutput(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_outputs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    project: Mapped[ResearchProject] = relationship(back_populates="outputs")


class PolicyStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Policy(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "policies"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    policy_area: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(30), default="national", nullable=False)
    ministry: Mapped[Optional[str]] = mapped_column(String(255))
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[PolicyStatus] = mapped_column(Enum(PolicyStatus, native_enum=False, length=20), default=PolicyStatus.DRAFT, nullable=False, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    geography: Mapped[Optional[str]] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    indicators: Mapped[List["PolicyIndicator"]] = relationship(back_populates="policy", cascade="all, delete-orphan")


class PolicyIndicator(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "policy_indicators"
    __table_args__ = (Index("ix_policy_indicator_code_period", "code", "period_start"),)

    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("policies.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"), index=True)
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    value_kind: Mapped[str] = mapped_column(String(20), default="OBSERVED", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    policy: Mapped[Optional[Policy]] = relationship(back_populates="indicators")
