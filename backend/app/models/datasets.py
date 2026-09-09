from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import ARRAY, Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class DatasetCategory(str, enum.Enum):
    LAND_USE = "land_use"
    AGRICULTURE = "agriculture"
    POPULATION = "population"
    INFRASTRUCTURE = "infrastructure"
    CLIMATE = "climate"
    SOCIO_ECONOMIC = "socio_economic"
    LAND_GOVERNANCE = "land_governance"
    DISPUTES = "disputes"
    PROJECT_OUTCOMES = "project_outcomes"
    REMOTE_SENSING = "remote_sensing"
    BOUNDARIES = "geospatial_boundaries"
    WATER = "water"
    FOREST = "forest"
    SOIL = "soil"


class DatasetStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DataSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000))
    organization: Mapped[Optional[str]] = mapped_column(String(255))
    license: Mapped[Optional[str]] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Dataset(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (Index("ix_datasets_category_status", "category", "status"),)

    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[DatasetCategory] = mapped_column(Enum(DatasetCategory, native_enum=False, length=40), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    geography: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    temporal_start: Mapped[Optional[date]] = mapped_column(Date)
    temporal_end: Mapped[Optional[date]] = mapped_column(Date)
    spatial_coverage: Mapped[Optional[str]] = mapped_column(String(255))
    spatial_resolution: Mapped[Optional[str]] = mapped_column(String(100))
    temporal_resolution: Mapped[Optional[str]] = mapped_column(String(100))
    format: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    license: Mapped[Optional[str]] = mapped_column(String(120))
    update_frequency: Mapped[Optional[str]] = mapped_column(String(50))
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    quality_notes: Mapped[Optional[str]] = mapped_column(Text)
    provenance: Mapped[Optional[str]] = mapped_column(Text)
    access_level: Mapped[str] = mapped_column(String(20), default="internal", nullable=False, index=True)
    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus, native_enum=False, length=20), default=DatasetStatus.DRAFT, nullable=False, index=True)
    keywords: Mapped[List[str]] = mapped_column(ARRAY(String(100)), default=list, nullable=False)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL", use_alter=True, name="fk_datasets_current_version"))
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versions: Mapped[List["DatasetVersion"]] = relationship(back_populates="dataset", cascade="all, delete-orphan", foreign_keys="DatasetVersion.dataset_id", order_by="DatasetVersion.version_number")
    variables: Mapped[List["DatasetVariable"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    source: Mapped[Optional[DataSource]] = relationship()


class DatasetVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[Optional[str]] = mapped_column(String(50))
    change_note: Mapped[Optional[str]] = mapped_column(Text)
    file_name: Mapped[Optional[str]] = mapped_column(String(500))
    storage_key: Mapped[Optional[str]] = mapped_column(String(1000))
    mime_type: Mapped[Optional[str]] = mapped_column(String(120))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_count: Mapped[Optional[int]] = mapped_column(Integer)
    schema_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    processing_status: Mapped[str] = mapped_column(String(20), default="UPLOADED", nullable=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship(back_populates="versions", foreign_keys=[dataset_id])


class DatasetVariable(UUIDMixin, Base):
    __tablename__ = "dataset_variables"
    __table_args__ = (UniqueConstraint("dataset_id", "code", name="uq_dataset_variable"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    data_type: Mapped[str] = mapped_column(String(30), default="number", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    dataset: Mapped[Dataset] = relationship(back_populates="variables")


class Observation(UUIDMixin, Base):
    """Tidy, analysable observations extracted from tabular dataset versions.

    Each row is one (variable, geography, period) value with its kind
    (OBSERVED / MODELLED / ASSUMPTION) so analytics and simulation can trace
    every number back to a dataset version.
    """

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_obs_var_unit_period", "variable_code", "admin_unit_id", "period_start"),
        Index("ix_obs_version", "dataset_version_id"),
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    variable_code: Mapped[str] = mapped_column(String(80), nullable=False)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    geography_label: Mapped[Optional[str]] = mapped_column(String(255))
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    value_kind: Mapped[str] = mapped_column(String(20), default="OBSERVED", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
