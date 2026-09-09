from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.knowledge import DocumentStatus, DocumentType, PolicyStatus, ProcessingStatus, ResearchStatus, Visibility
from app.schemas.common import ORMModel


class DocumentBase(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    abstract: Optional[str] = Field(None, max_length=20000)
    authors: List[str] = Field(default_factory=list)
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = Field(None, max_length=255)
    publication_date: Optional[date] = None
    document_type: DocumentType
    topic: Optional[str] = Field(None, max_length=120)
    policy_area: Optional[str] = Field(None, max_length=120)
    research_area: Optional[str] = Field(None, max_length=120)
    geography: Optional[str] = Field(None, max_length=255)
    admin_unit_id: Optional[uuid.UUID] = None
    keywords: List[str] = Field(default_factory=list)
    language: str = Field("en", max_length=20)
    source: Optional[str] = Field(None, max_length=255)
    source_url: Optional[str] = Field(None, max_length=1000)
    license: Optional[str] = Field(None, max_length=120)
    visibility: Visibility = Visibility.INTERNAL

    @field_validator("authors", "keywords")
    @classmethod
    def _clean_list(cls, v: List[str]) -> List[str]:
        return [s.strip()[:255] for s in v if s and s.strip()][:50]

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return v


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=500)
    description: Optional[str] = None
    abstract: Optional[str] = None
    authors: Optional[List[str]] = None
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = None
    publication_date: Optional[date] = None
    document_type: Optional[DocumentType] = None
    topic: Optional[str] = None
    policy_area: Optional[str] = None
    research_area: Optional[str] = None
    geography: Optional[str] = None
    admin_unit_id: Optional[uuid.UUID] = None
    keywords: Optional[List[str]] = None
    language: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    visibility: Optional[Visibility] = None


class DocumentVersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    version_label: Optional[str] = None
    change_note: Optional[str] = None
    file_name: str
    mime_type: str
    file_size: int
    checksum_sha256: str
    page_count: Optional[int] = None
    text_char_count: int
    processing_status: ProcessingStatus
    processing_error: Optional[str] = None
    processing_attempts: int
    ocr_applied: bool
    extracted_metadata: Optional[Dict[str, Any]] = None
    processed_at: Optional[datetime] = None
    created_at: datetime


class DocumentOut(ORMModel):
    id: uuid.UUID
    title: str
    slug: str
    description: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[str]
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = None
    publication_date: Optional[date] = None
    document_type: DocumentType
    topic: Optional[str] = None
    policy_area: Optional[str] = None
    research_area: Optional[str] = None
    geography: Optional[str] = None
    admin_unit_id: Optional[uuid.UUID] = None
    keywords: List[str]
    language: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    license: Optional[str] = None
    status: DocumentStatus
    visibility: Visibility
    current_version_id: Optional[uuid.UUID] = None
    created_by: uuid.UUID
    approved_by: Optional[uuid.UUID] = None
    published_at: Optional[datetime] = None
    download_count: int
    view_count: int
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentOut):
    versions: List[DocumentVersionOut] = []
    organization_name: Optional[str] = None
    related: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    processing_job: Optional[Dict[str, Any]] = None


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject|request_changes)$")
    comments: Optional[str] = Field(None, max_length=5000)


class RelationCreate(BaseModel):
    related_document_id: uuid.UUID
    relation_type: str = Field("related", max_length=40)


class ChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    page_start: Optional[int]
    page_end: Optional[int]
    content: str


# ---- research projects ----
class ResearchProjectCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    summary: Optional[str] = None
    research_area: Optional[str] = Field(None, max_length=120)
    geography: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    funding_source: Optional[str] = Field(None, max_length=255)
    keywords: List[str] = Field(default_factory=list)


class ResearchProjectUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    research_area: Optional[str] = None
    geography: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None
    status: Optional[ResearchStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    funding_source: Optional[str] = None
    keywords: Optional[List[str]] = None


class ResearchOutputCreate(BaseModel):
    output_type: str = Field(max_length=50)
    title: str = Field(min_length=2, max_length=500)
    description: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    dataset_id: Optional[uuid.UUID] = None


class ResearchOutputOut(ORMModel):
    id: uuid.UUID
    output_type: str
    title: str
    description: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    dataset_id: Optional[uuid.UUID] = None
    created_at: datetime


class ResearchProjectOut(ORMModel):
    id: uuid.UUID
    title: str
    summary: Optional[str] = None
    research_area: Optional[str] = None
    geography: Optional[str] = None
    lead_user_id: uuid.UUID
    organization_id: Optional[uuid.UUID] = None
    status: ResearchStatus
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    funding_source: Optional[str] = None
    keywords: List[str]
    is_demo: bool
    created_at: datetime
    outputs: List[ResearchOutputOut] = []


# ---- policies ----
class PolicyCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    summary: Optional[str] = None
    policy_area: str = Field(max_length=120)
    level: str = Field("national", pattern="^(national|state|district|international)$")
    ministry: Optional[str] = Field(None, max_length=255)
    effective_date: Optional[date] = None
    status: PolicyStatus = PolicyStatus.DRAFT
    document_id: Optional[uuid.UUID] = None
    geography: Optional[str] = Field(None, max_length=255)


class PolicyUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    policy_area: Optional[str] = None
    level: Optional[str] = None
    ministry: Optional[str] = None
    effective_date: Optional[date] = None
    status: Optional[PolicyStatus] = None
    document_id: Optional[uuid.UUID] = None
    geography: Optional[str] = None


class PolicyIndicatorCreate(BaseModel):
    code: str = Field(max_length=80)
    name: str = Field(max_length=255)
    unit: Optional[str] = Field(None, max_length=50)
    value: float
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    admin_unit_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    value_kind: str = Field("OBSERVED", pattern="^(OBSERVED|MODELLED|ASSUMPTION|SCENARIO)$")


class PolicyIndicatorOut(ORMModel):
    id: uuid.UUID
    policy_id: Optional[uuid.UUID] = None
    code: str
    name: str
    unit: Optional[str] = None
    value: float
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    admin_unit_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    value_kind: str
    is_demo: bool


class PolicyOut(ORMModel):
    id: uuid.UUID
    title: str
    slug: str
    summary: Optional[str] = None
    policy_area: str
    level: str
    ministry: Optional[str] = None
    effective_date: Optional[date] = None
    status: PolicyStatus
    document_id: Optional[uuid.UUID] = None
    geography: Optional[str] = None
    is_demo: bool
    created_at: datetime


class PolicyDetail(PolicyOut):
    indicators: List[PolicyIndicatorOut] = []
