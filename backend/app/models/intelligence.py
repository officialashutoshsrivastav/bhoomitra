from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Models registry (analytical + ML + simulation models, all versioned)
# ---------------------------------------------------------------------------
class AnalysisModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    versions: Mapped[List["ModelVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan", order_by="ModelVersion.created_at")


class ModelVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_version"),)

    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(120), nullable=False)
    features: Mapped[Optional[list]] = mapped_column(JSONB)
    input_description: Mapped[Optional[str]] = mapped_column(Text)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB)
    evaluation: Mapped[Optional[dict]] = mapped_column(JSONB)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    training_dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(1000))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    model: Mapped[AnalysisModel] = relationship(back_populates="versions")


class AnalyticsRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analytics_runs"

    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"), index=True)
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Evidence engine: recommendations -> evidence items -> provenance graph
# ---------------------------------------------------------------------------
class NodeType(str, enum.Enum):
    RECOMMENDATION = "recommendation"
    EVIDENCE = "evidence"
    DOCUMENT = "document"
    DOCUMENT_VERSION = "document_version"
    DOCUMENT_CHUNK = "document_chunk"
    DATASET = "dataset"
    DATASET_VERSION = "dataset_version"
    POLICY = "policy"
    GIS_LAYER = "gis_layer"
    GIS_FEATURE = "gis_feature"
    MODEL = "model"
    MODEL_VERSION = "model_version"
    ASSUMPTION = "assumption"
    SCENARIO = "scenario"
    SIMULATION_RUN = "simulation_run"
    ANALYTICS_RUN = "analytics_run"
    RS_PRODUCT = "rs_product"
    AI_MESSAGE = "ai_message"
    ADMIN_UNIT = "admin_unit"


class Recommendation(UUIDMixin, TimestampMixin, Base):
    """Any decision-support output the platform produced: AI answer, analytics
    insight, simulation finding. Never an official decision."""

    __tablename__ = "recommendations"

    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    confidence_basis: Mapped[Optional[str]] = mapped_column(Text)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    assumptions: Mapped[Optional[list]] = mapped_column(JSONB)
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    simulation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("simulation_runs.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    evidence: Mapped[List["EvidenceItem"]] = relationship(back_populates="recommendation", cascade="all, delete-orphan", order_by="EvidenceItem.rank")


class EvidenceItem(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_source", "source_type", "source_id"),)

    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_type: Mapped[NodeType] = mapped_column(Enum(NodeType, native_enum=False, length=30), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    locator: Mapped[Optional[str]] = mapped_column(String(255))
    score: Mapped[Optional[float]] = mapped_column(Float)
    value_kind: Mapped[str] = mapped_column(String(20), default="OBSERVED", nullable=False)

    recommendation: Mapped[Recommendation] = relationship(back_populates="evidence")


class ProvenanceLink(UUIDMixin, Base):
    __tablename__ = "provenance_links"
    __table_args__ = (
        UniqueConstraint("from_type", "from_id", "to_type", "to_id", "relation", name="uq_provenance_edge"),
        Index("ix_prov_from", "from_type", "from_id"),
        Index("ix_prov_to", "to_type", "to_id"),
    )

    from_type: Mapped[NodeType] = mapped_column(Enum(NodeType, native_enum=False, length=30), nullable=False)
    from_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    to_type: Mapped[NodeType] = mapped_column(Enum(NodeType, native_enum=False, length=30), nullable=False)
    to_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    relation: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Citation(UUIDMixin, Base):
    __tablename__ = "citations"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("document_chunks.id", ondelete="SET NULL"))
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"))
    marker: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    page: Mapped[Optional[int]] = mapped_column(Integer)
    score: Mapped[Optional[float]] = mapped_column(Float)


class Assumption(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assumptions"

    scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    low: Mapped[Optional[float]] = mapped_column(Float)
    high: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    basis: Mapped[Optional[str]] = mapped_column(Text)
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Policy simulation lab
# ---------------------------------------------------------------------------
class ScenarioStatus(str, enum.Enum):
    DRAFT = "draft"
    SIMULATED = "simulated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Scenario(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"), index=True)
    geography_label: Mapped[Optional[str]] = mapped_column(String(255))
    baseline_dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    baseline: Mapped[dict] = mapped_column(JSONB, nullable=False)
    interventions: Mapped[list] = mapped_column(JSONB, nullable=False)
    constraints: Mapped[Optional[dict]] = mapped_column(JSONB)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB)
    horizon_years: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    status: Mapped[ScenarioStatus] = mapped_column(Enum(ScenarioStatus, native_enum=False, length=20), default=ScenarioStatus.DRAFT, nullable=False, index=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    runs: Mapped[List["SimulationRun"]] = relationship(back_populates="scenario", cascade="all, delete-orphan", order_by="SimulationRun.created_at")
    assumptions: Mapped[List[Assumption]] = relationship(cascade="all, delete-orphan")


class SimulationRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "simulation_runs"

    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True)
    model_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    seed: Mapped[int] = mapped_column(Integer, default=42, nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    risks: Mapped[Optional[list]] = mapped_column(JSONB)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL", use_alter=True, name="fk_simulation_runs_recommendation"))

    scenario: Mapped[Scenario] = relationship(back_populates="runs")
    results: Mapped[List["SimulationResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SimulationResult(UUIDMixin, Base):
    __tablename__ = "simulation_results"
    __table_args__ = (Index("ix_sim_results_run_indicator", "run_id", "indicator_code", "year"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False)
    indicator_code: Mapped[str] = mapped_column(String(80), nullable=False)
    indicator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[Optional[float]] = mapped_column(Float)
    high: Mapped[Optional[float]] = mapped_column(Float)
    value_kind: Mapped[str] = mapped_column(String(20), nullable=False)

    run: Mapped[SimulationRun] = relationship(back_populates="results")


# ---------------------------------------------------------------------------
# AI assistant conversations
# ---------------------------------------------------------------------------
class AIConversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))

    messages: Mapped[List["AIMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at")


class AIMessage(UUIDMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    query_analysis: Mapped[Optional[dict]] = mapped_column(JSONB)
    retrieval: Mapped[Optional[dict]] = mapped_column(JSONB)
    provider: Mapped[Optional[str]] = mapped_column(String(50))
    model_name: Mapped[Optional[str]] = mapped_column(String(120))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    evidence_sufficient: Mapped[Optional[bool]] = mapped_column(Boolean)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    recommendation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")
    citations: Mapped[List[Citation]] = relationship(cascade="all, delete-orphan", order_by="Citation.marker")
