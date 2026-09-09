from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Collaborative workspaces
# ---------------------------------------------------------------------------
class WorkspaceStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    REVIEW = "review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


WORKSPACE_TRANSITIONS = {
    WorkspaceStatus.DRAFT: {WorkspaceStatus.ACTIVE, WorkspaceStatus.ARCHIVED},
    WorkspaceStatus.ACTIVE: {WorkspaceStatus.REVIEW, WorkspaceStatus.ARCHIVED},
    WorkspaceStatus.REVIEW: {WorkspaceStatus.ACTIVE, WorkspaceStatus.PUBLISHED, WorkspaceStatus.ARCHIVED},
    WorkspaceStatus.PUBLISHED: {WorkspaceStatus.ARCHIVED},
    WorkspaceStatus.ARCHIVED: {WorkspaceStatus.ACTIVE},
}


class Workspace(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[WorkspaceStatus] = mapped_column(Enum(WorkspaceStatus, native_enum=False, length=20), default=WorkspaceStatus.DRAFT, nullable=False, index=True)
    research_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    objective: Mapped[Optional[str]] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(String(60)))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    members: Mapped[List["WorkspaceMember"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    resources: Mapped[List["WorkspaceResource"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    workspace: Mapped[Workspace] = relationship(back_populates="members")


class WorkspaceResource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_resources"
    __table_args__ = (UniqueConstraint("workspace_id", "resource_type", "resource_id", name="uq_workspace_resource"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    workspace: Mapped[Workspace] = relationship(back_populates="resources")


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    workspace: Mapped[Workspace] = relationship(back_populates="tasks")


class Comment(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_target", "target_type", "target_id"),)

    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"))
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Activity(UUIDMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_workspace_time", "workspace_id", "created_at"),)

    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verb: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(30))
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Approval(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_target", "target_type", "target_id"),)

    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Innovation portal
# ---------------------------------------------------------------------------
class ChallengeStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    OPEN = "open"
    EVALUATION = "evaluation"
    SHORTLISTED = "shortlisted"
    PILOT = "pilot"
    COMPLETED = "completed"
    ARCHIVED = "archived"


CHALLENGE_TRANSITIONS = {
    ChallengeStatus.DRAFT: {ChallengeStatus.PUBLISHED, ChallengeStatus.ARCHIVED},
    ChallengeStatus.PUBLISHED: {ChallengeStatus.OPEN, ChallengeStatus.ARCHIVED},
    ChallengeStatus.OPEN: {ChallengeStatus.EVALUATION, ChallengeStatus.ARCHIVED},
    ChallengeStatus.EVALUATION: {ChallengeStatus.SHORTLISTED, ChallengeStatus.COMPLETED, ChallengeStatus.ARCHIVED},
    ChallengeStatus.SHORTLISTED: {ChallengeStatus.PILOT, ChallengeStatus.COMPLETED, ChallengeStatus.ARCHIVED},
    ChallengeStatus.PILOT: {ChallengeStatus.COMPLETED, ChallengeStatus.ARCHIVED},
    ChallengeStatus.COMPLETED: {ChallengeStatus.ARCHIVED},
    ChallengeStatus.ARCHIVED: set(),
}


class Challenge(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "challenges"

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    challenge_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    theme: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    eligibility: Mapped[Optional[str]] = mapped_column(Text)
    evaluation_criteria: Mapped[Optional[list]] = mapped_column(JSONB)
    prize_or_grant: Mapped[Optional[str]] = mapped_column(String(255))
    opens_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[ChallengeStatus] = mapped_column(Enum(ChallengeStatus, native_enum=False, length=20), default=ChallengeStatus.DRAFT, nullable=False, index=True)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    submissions: Mapped[List["Submission"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")


class Submission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "submissions"

    challenge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    applicant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    proposal: Mapped[Optional[str]] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    team_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    links: Mapped[Optional[list]] = mapped_column(JSONB)
    technical_details: Mapped[Optional[str]] = mapped_column(Text)
    expected_impact: Mapped[Optional[str]] = mapped_column(Text)
    budget_estimate: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float)
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    challenge: Mapped[Challenge] = relationship(back_populates="submissions")
    attachments: Mapped[List["SubmissionAttachment"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    evaluations: Mapped[List["Evaluation"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    pilots: Mapped[List["Pilot"]] = relationship(cascade="all, delete-orphan")


class SubmissionAttachment(UUIDMixin, Base):
    __tablename__ = "submission_attachments"

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="attachments")


class Evaluation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("submission_id", "evaluator_id", name="uq_evaluation_per_evaluator"),)

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    comments: Mapped[Optional[str]] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(20), default="undecided", nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="evaluations")


class Pilot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pilots"

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    challenge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    admin_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("admin_units.id", ondelete="SET NULL"))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    outcome_summary: Mapped[Optional[str]] = mapped_column(Text)
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    budget: Mapped[Optional[float]] = mapped_column(Float)
    kpis: Mapped[Optional[list]] = mapped_column(JSONB)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class Notification(UUIDMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(500))
    channel: Mapped[str] = mapped_column(String(20), default="in_app", nullable=False)
    email_status: Mapped[Optional[str]] = mapped_column(String(20))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Audit log (append-only)
# ---------------------------------------------------------------------------
class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_user_time", "user_id", "created_at"),
        Index("ix_audit_action_time", "action", "created_at"),
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    user_email: Mapped[Optional[str]] = mapped_column(String(255))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(64))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    detail: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Background jobs
# ---------------------------------------------------------------------------
class BackgroundJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (Index("ix_jobs_status_type", "status", "job_type"),)

    job_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(40))
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(80))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------
class SavedSearch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "saved_searches"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB)


class SearchHistory(UUIDMixin, Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_time", "user_id", "created_at"),)

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Reports and integrations
# ---------------------------------------------------------------------------
class Report(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB)
    data_period_start: Mapped[Optional[date]] = mapped_column(Date)
    data_period_end: Mapped[Optional[date]] = mapped_column(Date)
    methodology: Mapped[Optional[str]] = mapped_column(Text)
    storage_key: Mapped[Optional[str]] = mapped_column(String(1000))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    sources: Mapped[Optional[list]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)


class IntegrationConfig(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "integrations"

    connector: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="demo", nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[Optional[str]] = mapped_column(String(20))
    last_message: Mapped[Optional[str]] = mapped_column(Text)
