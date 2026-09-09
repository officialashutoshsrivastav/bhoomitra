from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, TimestampMixin, UUIDMixin


class AdminLevel(str, enum.Enum):
    COUNTRY = "country"
    STATE = "state"
    DISTRICT = "district"
    SUBDISTRICT = "subdistrict"
    VILLAGE = "village"


LEVEL_ORDER = {AdminLevel.COUNTRY: 0, AdminLevel.STATE: 1, AdminLevel.DISTRICT: 2, AdminLevel.SUBDISTRICT: 3, AdminLevel.VILLAGE: 4}


class AdminUnit(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "admin_units"
    __table_args__ = (
        UniqueConstraint("level", "code", name="uq_admin_unit_level_code"),
        Index("ix_admin_units_geom", "geom", postgresql_using="gist"),
        Index("ix_admin_units_parent_level", "parent_id", "level"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[AdminLevel] = mapped_column(Enum(AdminLevel, native_enum=False, length=20), nullable=False, index=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="CASCADE"))
    geom: Mapped[Optional[object]] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False))
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    area_km2: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(255))
    source_license: Mapped[Optional[str]] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    parent: Mapped[Optional["AdminUnit"]] = relationship(remote_side="AdminUnit.id", backref="children")


class LayerCategory(str, enum.Enum):
    LAND_USE = "land_use"
    AGRICULTURE = "agriculture"
    FOREST = "forest"
    WATER = "water"
    ROADS = "roads"
    RAILWAYS = "railways"
    INFRASTRUCTURE = "infrastructure"
    URBAN = "urban"
    POPULATION = "population"
    CLIMATE_RISK = "climate_risk"
    VULNERABILITY = "vulnerability"
    PROJECTS = "projects"
    SOIL = "soil"
    ELEVATION = "elevation"
    BOUNDARY = "boundary"
    OTHER = "other"


class GISLayer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "gis_layers"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[LayerCategory] = mapped_column(Enum(LayerCategory, native_enum=False, length=30), nullable=False, index=True)
    geometry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    source: Mapped[Optional[str]] = mapped_column(String(255))
    source_license: Mapped[Optional[str]] = mapped_column(String(120))
    value_field: Mapped[Optional[str]] = mapped_column(String(80))
    class_field: Mapped[Optional[str]] = mapped_column(String(80))
    legend: Mapped[Optional[dict]] = mapped_column(JSONB)
    style: Mapped[Optional[dict]] = mapped_column(JSONB)
    temporal_start: Mapped[Optional[date]] = mapped_column(Date)
    temporal_end: Mapped[Optional[date]] = mapped_column(Date)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    feature_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    features: Mapped[List["GISFeature"]] = relationship(back_populates="layer", cascade="all, delete-orphan")


class GISFeature(UUIDMixin, Base):
    __tablename__ = "gis_features"
    __table_args__ = (
        Index("ix_gis_features_geom", "geom", postgresql_using="gist"),
        Index("ix_gis_features_layer_class", "layer_id", "class_value"),
        Index("ix_gis_features_layer_time", "layer_id", "valid_from"),
    )

    layer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gis_layers.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    class_value: Mapped[Optional[str]] = mapped_column(String(120))
    numeric_value: Mapped[Optional[float]] = mapped_column(Float)
    properties: Mapped[Optional[dict]] = mapped_column(JSONB)
    geom: Mapped[object] = mapped_column(Geometry(srid=4326, spatial_index=False), nullable=False)
    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    layer: Mapped[GISLayer] = relationship(back_populates="features")


class SpatialAnalysisRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "spatial_analysis_runs"

    operation: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    result_geom: Mapped[Optional[object]] = mapped_column(Geometry(srid=4326, spatial_index=False))
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RSScene(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rs_scenes"
    __table_args__ = (UniqueConstraint("source", "scene_id", name="uq_rs_scene"), Index("ix_rs_scenes_bounds", "bounds", postgresql_using="gist"))

    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scene_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acquisition_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    resolution_m: Mapped[Optional[float]] = mapped_column(Float)
    cloud_cover: Mapped[Optional[float]] = mapped_column(Float)
    bounds: Mapped[Optional[object]] = mapped_column(Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False))
    bands: Mapped[Optional[dict]] = mapped_column(JSONB)
    asset_uri: Mapped[Optional[str]] = mapped_column(String(1000))
    processing_status: Mapped[str] = mapped_column(String(20), default="REGISTERED", nullable=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    provenance: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    products: Mapped[List["RSProduct"]] = relationship(back_populates="scene", cascade="all, delete-orphan")


class RSProduct(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rs_products"

    scene_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rs_scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    statistics: Mapped[Optional[dict]] = mapped_column(JSONB)
    raster_uri: Mapped[Optional[str]] = mapped_column(String(1000))
    method: Mapped[Optional[str]] = mapped_column(String(255))
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="READY", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scene: Mapped[RSScene] = relationship(back_populates="products")
