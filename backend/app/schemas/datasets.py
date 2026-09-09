from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.datasets import DatasetCategory, DatasetStatus
from app.schemas.common import ORMModel


class DataSourceCreate(BaseModel):
    name: str = Field(max_length=255)
    source_type: str = Field(max_length=50)
    url: Optional[str] = Field(None, max_length=1000)
    organization: Optional[str] = Field(None, max_length=255)
    license: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    is_official: bool = False


class DataSourceOut(ORMModel):
    id: uuid.UUID
    name: str
    source_type: str
    url: Optional[str] = None
    organization: Optional[str] = None
    license: Optional[str] = None
    description: Optional[str] = None
    is_official: bool
    is_demo: bool


class DatasetVariableIn(BaseModel):
    code: str = Field(max_length=80)
    name: str = Field(max_length=255)
    unit: Optional[str] = Field(None, max_length=50)
    data_type: str = Field("number", max_length=30)
    description: Optional[str] = None


class DatasetVariableOut(DatasetVariableIn, ORMModel):
    id: uuid.UUID


class DatasetCreate(BaseModel):
    name: str = Field(min_length=3, max_length=500)
    description: Optional[str] = None
    category: DatasetCategory
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = Field(None, max_length=255)
    source_id: Optional[uuid.UUID] = None
    geography: Optional[str] = Field(None, max_length=255)
    admin_unit_id: Optional[uuid.UUID] = None
    temporal_start: Optional[date] = None
    temporal_end: Optional[date] = None
    spatial_coverage: Optional[str] = Field(None, max_length=255)
    spatial_resolution: Optional[str] = Field(None, max_length=100)
    temporal_resolution: Optional[str] = Field(None, max_length=100)
    format: Optional[str] = Field(None, max_length=50)
    license: Optional[str] = Field(None, max_length=120)
    update_frequency: Optional[str] = Field(None, max_length=50)
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    quality_notes: Optional[str] = None
    provenance: Optional[str] = None
    access_level: str = Field("internal", pattern="^(public|open|internal|restricted)$")
    keywords: List[str] = Field(default_factory=list)
    variables: List[DatasetVariableIn] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def _kw(cls, v):
        return [s.strip()[:100] for s in v if s and s.strip()][:50]


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[DatasetCategory] = None
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = None
    source_id: Optional[uuid.UUID] = None
    geography: Optional[str] = None
    admin_unit_id: Optional[uuid.UUID] = None
    temporal_start: Optional[date] = None
    temporal_end: Optional[date] = None
    spatial_coverage: Optional[str] = None
    spatial_resolution: Optional[str] = None
    temporal_resolution: Optional[str] = None
    format: Optional[str] = None
    license: Optional[str] = None
    update_frequency: Optional[str] = None
    quality_score: Optional[float] = Field(None, ge=0, le=1)
    quality_notes: Optional[str] = None
    provenance: Optional[str] = None
    access_level: Optional[str] = Field(None, pattern="^(public|open|internal|restricted)$")
    keywords: Optional[List[str]] = None


class DatasetVersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    version_label: Optional[str] = None
    change_note: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    checksum_sha256: Optional[str] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    schema_snapshot: Optional[Dict[str, Any]] = None
    processing_status: str
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime


class DatasetOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str] = None
    category: DatasetCategory
    owner_id: uuid.UUID
    organization_id: Optional[uuid.UUID] = None
    publisher: Optional[str] = None
    source_id: Optional[uuid.UUID] = None
    geography: Optional[str] = None
    admin_unit_id: Optional[uuid.UUID] = None
    temporal_start: Optional[date] = None
    temporal_end: Optional[date] = None
    spatial_coverage: Optional[str] = None
    spatial_resolution: Optional[str] = None
    temporal_resolution: Optional[str] = None
    format: Optional[str] = None
    license: Optional[str] = None
    update_frequency: Optional[str] = None
    quality_score: Optional[float] = None
    quality_notes: Optional[str] = None
    provenance: Optional[str] = None
    access_level: str
    status: DatasetStatus
    keywords: List[str]
    current_version_id: Optional[uuid.UUID] = None
    download_count: int
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetOut):
    versions: List[DatasetVersionOut] = []
    variables: List[DatasetVariableOut] = []
    source: Optional[DataSourceOut] = None
    observation_count: int = 0


class ObservationOut(BaseModel):
    variable_code: str
    geography_label: Optional[str]
    admin_unit_id: Optional[uuid.UUID]
    period_start: Optional[date]
    period_end: Optional[date]
    value: float
    unit: Optional[str]
    value_kind: str
    is_demo: bool
