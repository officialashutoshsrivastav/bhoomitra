"""platform extensions: workspace/task/comment/activity/innovation columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("comments", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pilots", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("pilots", sa.Column("budget", sa.Float(), nullable=True))
    op.add_column("pilots", sa.Column("kpis", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("pilots", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("submission_attachments", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
    op.add_column("submissions", sa.Column("abstract", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("team_name", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("submissions", sa.Column("decision_note", sa.Text(), nullable=True))
    op.alter_column("submissions", "proposal", existing_type=sa.Text(), nullable=True)
    op.alter_column("submissions", "submitted_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workspace_members", sa.Column("invited_by", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_workspace_members_invited_by", "workspace_members", "users", ["invited_by"], ["id"], ondelete="SET NULL")
    op.add_column("workspaces", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("workspaces", sa.Column("tags", postgresql.ARRAY(sa.String(length=60)), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "tags")
    op.drop_column("workspaces", "is_public")
    op.drop_column("workspaces", "objective")
    op.drop_constraint("fk_workspace_members_invited_by", "workspace_members", type_="foreignkey")
    op.drop_column("workspace_members", "invited_by")
    op.drop_column("tasks", "completed_at")
    op.execute("UPDATE submissions SET submitted_at = created_at WHERE submitted_at IS NULL")
    op.execute("UPDATE submissions SET proposal = COALESCE(abstract, '') WHERE proposal IS NULL")
    op.alter_column("submissions", "submitted_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("submissions", "proposal", existing_type=sa.Text(), nullable=False)
    op.drop_column("submissions", "decision_note")
    op.drop_column("submissions", "links")
    op.drop_column("submissions", "contact_email")
    op.drop_column("submissions", "team_name")
    op.drop_column("submissions", "abstract")
    op.drop_column("submission_attachments", "checksum_sha256")
    op.drop_column("pilots", "is_demo")
    op.drop_column("pilots", "kpis")
    op.drop_column("pilots", "budget")
    op.drop_column("pilots", "description")
    op.drop_column("comments", "edited_at")
    op.drop_column("activities", "detail")
