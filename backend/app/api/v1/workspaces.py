from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_permissions, require_permissions
from app.audit import service as audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.platform import WORKSPACE_TRANSITIONS, Activity, Approval, Comment, Task, Workspace, WorkspaceMember, WorkspaceResource, WorkspaceStatus
from app.notifications.service import notify, notify_many
from app.schemas.common import Message, Page, PageParams
from app.services.document_service import unique_slug

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

RESOURCE_TYPES = {"document", "dataset", "scenario", "analytics_run", "gis_layer", "policy", "research_project", "ai_conversation", "report"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    objective: Optional[str] = None
    organization_id: Optional[uuid.UUID] = None
    is_public: bool = False
    tags: List[str] = Field(default_factory=list)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    objective: Optional[str] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class MemberIn(BaseModel):
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = None
    role: str = Field("contributor", pattern="^(owner|editor|contributor|viewer)$")


class ResourceIn(BaseModel):
    resource_type: str = Field(max_length=40)
    resource_id: uuid.UUID
    title: Optional[str] = Field(None, max_length=500)
    note: Optional[str] = None


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=500)
    description: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    due_date: Optional[date] = None
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[uuid.UUID] = None
    due_date: Optional[date] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    status: Optional[str] = Field(None, pattern="^(todo|in_progress|blocked|done|cancelled)$")


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    target_type: str = Field("workspace", max_length=40)
    target_id: Optional[uuid.UUID] = None
    parent_id: Optional[uuid.UUID] = None


class TransitionIn(BaseModel):
    status: WorkspaceStatus
    note: Optional[str] = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ws(db: Session, ws_id: uuid.UUID) -> Workspace:
    ws = db.scalar(select(Workspace).options(selectinload(Workspace.members)).execution_options(populate_existing=True).where(Workspace.id == ws_id, Workspace.deleted_at.is_(None)))
    if not ws:
        raise NotFoundError("Workspace not found")
    return ws


def _member(ws: Workspace, user: User) -> Optional[WorkspaceMember]:
    return next((m for m in ws.members if m.user_id == user.id), None)


def _require_access(ws: Workspace, user: User, perms: set, write: bool = False) -> WorkspaceMember | None:
    m = _member(ws, user)
    if user.is_superuser or P.WORKSPACE_MANAGE in perms:
        return m
    if m is None:
        if ws.is_public and not write and ws.status in (WorkspaceStatus.PUBLISHED, WorkspaceStatus.ACTIVE):
            return None
        raise ForbiddenError("You are not a member of this workspace")
    if write and m.role == "viewer":
        raise ForbiddenError("Viewers cannot modify the workspace")
    return m


def _require_owner(ws: Workspace, user: User, perms: set) -> None:
    m = _member(ws, user)
    if not (user.is_superuser or P.WORKSPACE_MANAGE in perms or ws.owner_id == user.id or (m and m.role == "owner")):
        raise ForbiddenError("Only workspace owners can do this")


def _activity(db: Session, ws: Workspace, user: User, action: str, target_type: Optional[str] = None, target_id: Optional[uuid.UUID] = None, detail: Optional[Dict[str, Any]] = None) -> None:
    summary = f"{user.full_name} · {action.replace('.', ' ').replace('_', ' ')}"
    if detail and detail.get("title"):
        summary += f": {detail['title']}"
    db.add(Activity(workspace_id=ws.id, actor_id=user.id, verb=action, target_type=target_type, target_id=target_id, summary=summary[:500], detail=detail))


def _ws_dict(db: Session, ws: Workspace, user: Optional[User] = None) -> Dict[str, Any]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_([m.user_id for m in ws.members] + [ws.owner_id]))).all()}
    return {
        "id": str(ws.id), "name": ws.name, "slug": ws.slug, "description": ws.description, "objective": ws.objective, "status": ws.status.value, "is_public": ws.is_public, "tags": ws.tags or [], "owner_id": str(ws.owner_id), "organization_id": str(ws.organization_id) if ws.organization_id else None, "created_at": ws.created_at.isoformat(), "updated_at": ws.updated_at.isoformat(), "is_demo": ws.is_demo,
        "members": [{"user_id": str(m.user_id), "role": m.role, "name": users[m.user_id].full_name if m.user_id in users else None, "email": users[m.user_id].email if m.user_id in users else None, "joined_at": m.added_at.isoformat()} for m in ws.members],
        "my_role": next((m.role for m in ws.members if user and m.user_id == user.id), None),
        "counts": {"resources": db.scalar(select(func.count(WorkspaceResource.id)).where(WorkspaceResource.workspace_id == ws.id)) or 0, "tasks_open": db.scalar(select(func.count(Task.id)).where(Task.workspace_id == ws.id, Task.status.in_(["todo", "in_progress", "blocked"]))) or 0, "comments": db.scalar(select(func.count(Comment.id)).where(Comment.workspace_id == ws.id)) or 0},
        "allowed_transitions": [s.value for s in WORKSPACE_TRANSITIONS.get(ws.status, [])],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
def list_workspaces(page: PageParams = Depends(), q: Optional[str] = None, status_filter: Annotated[Optional[WorkspaceStatus], Query(alias="status")] = None, mine: bool = False, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    member_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    stmt = select(Workspace).options(selectinload(Workspace.members)).where(Workspace.deleted_at.is_(None))
    if mine:
        stmt = stmt.where(or_(Workspace.id.in_(member_ids), Workspace.owner_id == user.id))
    elif not (user.is_superuser or P.WORKSPACE_MANAGE in perms):
        stmt = stmt.where(or_(Workspace.id.in_(member_ids), Workspace.owner_id == user.id, Workspace.is_public.is_(True)))
    if q:
        stmt = stmt.where(or_(Workspace.name.ilike(f"%{q}%"), Workspace.description.ilike(f"%{q}%")))
    if status_filter:
        stmt = stmt.where(Workspace.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Workspace.updated_at.desc()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([_ws_dict(db, w, user) for w in rows], total, page.page, page.page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, request: Request, user: User = Depends(require_permissions(P.WORKSPACE_CREATE)), db: Session = Depends(get_db)):
    ws = Workspace(**payload.model_dump(), slug=unique_slug(db, Workspace, payload.name), owner_id=user.id, status=WorkspaceStatus.DRAFT)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", invited_by=user.id))
    _activity(db, ws, user, "workspace.created")
    audit.record(db, "workspace.create", user=user, resource_type="workspace", resource_id=ws.id, request=request)
    db.commit()
    return _ws_dict(db, _ws(db, ws.id), user)


@router.get("/{ws_id}")
def get_workspace(ws_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms)
    return _ws_dict(db, ws, user)


@router.patch("/{ws_id}")
def update_workspace(ws_id: uuid.UUID, payload: WorkspaceUpdate, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(ws, k, v)
    _activity(db, ws, user, "workspace.updated", detail={"fields": list(changes)})
    audit.record(db, "workspace.update", user=user, resource_type="workspace", resource_id=ws.id, request=request)
    db.commit()
    return _ws_dict(db, _ws(db, ws.id), user)


@router.post("/{ws_id}/transition")
def transition(ws_id: uuid.UUID, payload: TransitionIn, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_owner(ws, user, perms)
    if payload.status not in WORKSPACE_TRANSITIONS.get(ws.status, []):
        raise ConflictError(f"Cannot move workspace from {ws.status.value} to {payload.status.value}")
    if payload.status == WorkspaceStatus.PUBLISHED and P.WORKSPACE_MANAGE not in perms and not user.is_superuser:
        # publishing needs an approval record; owners submit, managers approve
        pending = db.scalar(select(Approval).where(Approval.target_type == "workspace", Approval.target_id == ws.id, Approval.status == "approved").order_by(Approval.created_at.desc()))
        if not pending:
            raise ForbiddenError("Publishing requires an approved review request (submit for review first)")
    if payload.status == WorkspaceStatus.REVIEW:
        db.add(Approval(target_type="workspace", target_id=ws.id, title=f"Publish workspace: {ws.name}", requested_by=user.id))
        managers = db.scalars(select(User.id).where(User.is_superuser.is_(True))).all()
        notify_many(db, list(managers), "approval", "Workspace awaiting review", ws.name, link=f"/app/workspaces/{ws.id}")
    old = ws.status
    ws.status = payload.status
    _activity(db, ws, user, "workspace.status_changed", detail={"from": old.value, "to": payload.status.value, "note": payload.note})
    audit.record(db, "workspace.transition", user=user, resource_type="workspace", resource_id=ws.id, detail={"from": old.value, "to": payload.status.value}, request=request)
    db.commit()
    return _ws_dict(db, _ws(db, ws.id), user)


@router.delete("/{ws_id}", response_model=Message)
def delete_workspace(ws_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_owner(ws, user, perms)
    ws.deleted_at = _now()
    audit.record(db, "workspace.delete", user=user, resource_type="workspace", resource_id=ws.id, request=request)
    db.commit()
    return Message(message="Workspace deleted")


# ---- members ----
@router.post("/{ws_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(ws_id: uuid.UUID, payload: MemberIn, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_owner(ws, user, perms)
    target = db.get(User, payload.user_id) if payload.user_id else (db.scalar(select(User).where(User.email == payload.email.lower())) if payload.email else None)
    if not target:
        raise NotFoundError("User not found")
    if _member(ws, target):
        raise ConflictError("User is already a member")
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=target.id, role=payload.role, invited_by=user.id))
    _activity(db, ws, user, "member.added", "user", target.id, {"role": payload.role})
    notify(db, target.id, "workspace", "Added to workspace", f"You were added to '{ws.name}' as {payload.role}", link=f"/app/workspaces/{ws.id}", email=True)
    audit.record(db, "workspace.member_add", user=user, resource_type="workspace", resource_id=ws.id, detail={"user": str(target.id), "role": payload.role}, request=request)
    db.commit()
    return _ws_dict(db, _ws(db, ws.id), user)


@router.patch("/{ws_id}/members/{member_user_id}")
def update_member(ws_id: uuid.UUID, member_user_id: uuid.UUID, role: Annotated[str, Query(pattern="^(owner|editor|contributor|viewer)$")], user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_owner(ws, user, perms)
    m = next((m for m in ws.members if m.user_id == member_user_id), None)
    if not m:
        raise NotFoundError("Member not found")
    m.role = role
    _activity(db, ws, user, "member.role_changed", "user", member_user_id, {"role": role})
    db.commit()
    return _ws_dict(db, _ws(db, ws.id), user)


@router.delete("/{ws_id}/members/{member_user_id}", response_model=Message)
def remove_member(ws_id: uuid.UUID, member_user_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    if member_user_id != user.id:
        _require_owner(ws, user, perms)
    m = next((m for m in ws.members if m.user_id == member_user_id), None)
    if not m:
        raise NotFoundError("Member not found")
    if m.user_id == ws.owner_id:
        raise ConflictError("The workspace owner cannot be removed")
    db.delete(m)
    _activity(db, ws, user, "member.removed", "user", member_user_id)
    db.commit()
    return Message(message="Member removed")


# ---- resources ----
@router.get("/{ws_id}/resources")
def list_resources(ws_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms)
    rows = db.scalars(select(WorkspaceResource).where(WorkspaceResource.workspace_id == ws.id).order_by(WorkspaceResource.created_at.desc())).all()
    return {"items": [{"id": str(r.id), "resource_type": r.resource_type, "resource_id": str(r.resource_id), "title": r.title, "note": r.note, "added_by": str(r.added_by), "created_at": r.created_at.isoformat()} for r in rows]}


@router.post("/{ws_id}/resources", status_code=status.HTTP_201_CREATED)
def add_resource(ws_id: uuid.UUID, payload: ResourceIn, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    if payload.resource_type not in RESOURCE_TYPES:
        raise ValidationFailed(f"resource_type must be one of {sorted(RESOURCE_TYPES)}")
    exists = db.scalar(select(WorkspaceResource.id).where(WorkspaceResource.workspace_id == ws.id, WorkspaceResource.resource_type == payload.resource_type, WorkspaceResource.resource_id == payload.resource_id))
    if exists:
        raise ConflictError("Resource already linked")
    r = WorkspaceResource(workspace_id=ws.id, added_by=user.id, **payload.model_dump())
    db.add(r)
    _activity(db, ws, user, "resource.added", payload.resource_type, payload.resource_id, {"title": payload.title})
    db.commit()
    return {"id": str(r.id), "resource_type": r.resource_type, "resource_id": str(r.resource_id), "title": r.title}


@router.delete("/{ws_id}/resources/{res_id}", response_model=Message)
def remove_resource(ws_id: uuid.UUID, res_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    r = db.get(WorkspaceResource, res_id)
    if not r or r.workspace_id != ws.id:
        raise NotFoundError("Resource link not found")
    db.delete(r)
    _activity(db, ws, user, "resource.removed", r.resource_type, r.resource_id)
    db.commit()
    return Message(message="Resource unlinked")


# ---- tasks ----
def _task_dict(t: Task) -> Dict[str, Any]:
    return {"id": str(t.id), "title": t.title, "description": t.description, "status": t.status, "priority": t.priority, "assignee_id": str(t.assignee_id) if t.assignee_id else None, "created_by": str(t.created_by), "due_date": t.due_date.isoformat() if t.due_date else None, "completed_at": t.completed_at.isoformat() if t.completed_at else None, "created_at": t.created_at.isoformat()}


@router.get("/{ws_id}/tasks")
def list_tasks(ws_id: uuid.UUID, status_filter: Annotated[Optional[str], Query(alias="status")] = None, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms)
    stmt = select(Task).where(Task.workspace_id == ws.id)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    return {"items": [_task_dict(t) for t in db.scalars(stmt.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())).all()]}


@router.post("/{ws_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_task(ws_id: uuid.UUID, payload: TaskIn, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    t = Task(workspace_id=ws.id, created_by=user.id, **payload.model_dump())
    db.add(t)
    db.flush()
    _activity(db, ws, user, "task.created", "task", t.id, {"title": t.title})
    if t.assignee_id and t.assignee_id != user.id:
        notify(db, t.assignee_id, "task", "Task assigned", f"{t.title} in {ws.name}", link=f"/app/workspaces/{ws.id}")
    db.commit()
    return _task_dict(t)


@router.patch("/{ws_id}/tasks/{task_id}")
def update_task(ws_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    t = db.get(Task, task_id)
    if not t or t.workspace_id != ws.id:
        raise NotFoundError("Task not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t, k, v)
    if changes.get("status") == "done":
        t.completed_at = _now()
    _activity(db, ws, user, "task.updated", "task", t.id, changes if "status" not in changes else {"status": changes["status"]})
    db.commit()
    return _task_dict(t)


# ---- comments ----
def _comment_dict(c: Comment, users: Dict[uuid.UUID, User]) -> Dict[str, Any]:
    return {"id": str(c.id), "body": c.body, "author_id": str(c.author_id), "author_name": users[c.author_id].full_name if c.author_id in users else None, "target_type": c.target_type, "target_id": str(c.target_id) if c.target_id else None, "parent_id": str(c.parent_id) if c.parent_id else None, "created_at": c.created_at.isoformat(), "edited_at": c.edited_at.isoformat() if c.edited_at else None}


@router.get("/{ws_id}/comments")
def list_comments(ws_id: uuid.UUID, target_type: Optional[str] = None, target_id: Optional[uuid.UUID] = None, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms)
    stmt = select(Comment).where(Comment.workspace_id == ws.id, Comment.deleted_at.is_(None))
    if target_type:
        stmt = stmt.where(Comment.target_type == target_type)
    if target_id:
        stmt = stmt.where(Comment.target_id == target_id)
    rows = db.scalars(stmt.order_by(Comment.created_at.asc())).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({c.author_id for c in rows}))).all()} if rows else {}
    return {"items": [_comment_dict(c, users) for c in rows]}


@router.post("/{ws_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(ws_id: uuid.UUID, payload: CommentIn, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms, write=True)
    c = Comment(workspace_id=ws.id, author_id=user.id, body=payload.body, target_type=payload.target_type, target_id=payload.target_id or ws.id, parent_id=payload.parent_id)
    db.add(c)
    db.flush()
    _activity(db, ws, user, "comment.added", payload.target_type, c.target_id)
    others = [m.user_id for m in ws.members if m.user_id != user.id]
    notify_many(db, others, "comment", f"New comment in {ws.name}", payload.body[:140], link=f"/app/workspaces/{ws.id}")
    db.commit()
    return _comment_dict(c, {user.id: user})


@router.delete("/{ws_id}/comments/{comment_id}", response_model=Message)
def delete_comment(ws_id: uuid.UUID, comment_id: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    c = db.get(Comment, comment_id)
    if not c or c.workspace_id != ws.id:
        raise NotFoundError("Comment not found")
    if c.author_id != user.id:
        _require_owner(ws, user, perms)
    c.deleted_at = _now()
    db.commit()
    return Message(message="Comment removed")


# ---- activity ----
@router.get("/{ws_id}/activity")
def activity(ws_id: uuid.UUID, limit: Annotated[int, Query(le=200)] = 50, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ws = _ws(db, ws_id)
    _require_access(ws, user, perms)
    rows = db.scalars(select(Activity).where(Activity.workspace_id == ws.id).order_by(Activity.created_at.desc()).limit(limit)).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.actor_id for a in rows if a.actor_id}))).all()} if rows else {}
    return {"items": [{"id": str(a.id), "action": a.verb, "summary": a.summary, "actor_id": str(a.actor_id) if a.actor_id else None, "actor_name": users[a.actor_id].full_name if a.actor_id in users else None, "target_type": a.target_type, "target_id": str(a.target_id) if a.target_id else None, "detail": a.detail, "created_at": a.created_at.isoformat()} for a in rows]}
