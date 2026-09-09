from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_current_user_optional, get_permissions, require_permissions
from app.audit import service as audit
from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import P
from app.db.database import get_db
from app.models.identity import User
from app.models.platform import CHALLENGE_TRANSITIONS, Challenge, ChallengeStatus, Evaluation, Pilot, Submission, SubmissionAttachment
from app.notifications.service import notify
from app.schemas.common import Message, Page, PageParams
from app.search import indexer
from app.services.document_service import unique_slug
from app.storage.service import build_key, get_storage, read_upload, sha256_bytes
from app.storage.validation import validate_upload

router = APIRouter(prefix="/innovation", tags=["innovation"])
challenges_router = APIRouter(prefix="/challenges", tags=["innovation"])
submissions_router = APIRouter(prefix="/submissions", tags=["innovation"])

PUBLIC_STATUSES = [ChallengeStatus.PUBLISHED, ChallengeStatus.OPEN, ChallengeStatus.EVALUATION, ChallengeStatus.SHORTLISTED, ChallengeStatus.PILOT, ChallengeStatus.COMPLETED]
DEFAULT_CRITERIA = [{"code": "relevance", "label": "Relevance to land governance problem", "weight": 0.25, "max": 10}, {"code": "feasibility", "label": "Technical & institutional feasibility", "weight": 0.25, "max": 10}, {"code": "impact", "label": "Expected impact & scalability", "weight": 0.3, "max": 10}, {"code": "evidence", "label": "Evidence base & data use", "weight": 0.2, "max": 10}]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    summary: Optional[str] = Field(None, max_length=2000)
    description: Optional[str] = None
    challenge_type: str = Field("innovation_challenge", pattern="^(innovation_challenge|research_call|pilot_programme|hackathon|expression_of_interest)$")
    theme: Optional[str] = Field(None, max_length=120)
    organization_id: Optional[uuid.UUID] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    evaluation_criteria: Optional[List[Dict[str, Any]]] = None
    eligibility: Optional[str] = None
    prize_or_grant: Optional[str] = Field(None, max_length=255)


class ChallengeUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    theme: Optional[str] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    evaluation_criteria: Optional[List[Dict[str, Any]]] = None
    eligibility: Optional[str] = None
    prize_or_grant: Optional[str] = None


class TransitionIn(BaseModel):
    status: ChallengeStatus
    note: Optional[str] = Field(None, max_length=2000)


class SubmissionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    abstract: Optional[str] = Field(None, max_length=5000)
    proposal: Optional[str] = None
    team_name: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[uuid.UUID] = None
    contact_email: Optional[str] = None
    links: Optional[List[str]] = None


class EvaluationIn(BaseModel):
    scores: Dict[str, float]
    comments: Optional[str] = Field(None, max_length=8000)
    recommendation: str = Field("consider", pattern="^(shortlist|consider|reject)$")


class PilotIn(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    description: Optional[str] = None
    admin_unit_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    kpis: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _challenge(db: Session, cid: uuid.UUID) -> Challenge:
    c = db.scalar(select(Challenge).options(selectinload(Challenge.submissions)).execution_options(populate_existing=True).where(Challenge.id == cid, Challenge.deleted_at.is_(None)))
    if not c:
        raise NotFoundError("Challenge not found")
    return c


def _can_manage(c: Challenge, user: User, perms: set) -> bool:
    return user.is_superuser or P.INNOVATION_MANAGE in perms or c.created_by == user.id


def _challenge_dict(db: Session, c: Challenge, user: Optional[User] = None) -> Dict[str, Any]:
    sub_count = db.scalar(select(func.count(Submission.id)).where(Submission.challenge_id == c.id, Submission.status != "draft")) or 0
    return {"id": str(c.id), "title": c.title, "slug": c.slug, "summary": c.summary, "description": c.description, "challenge_type": c.challenge_type, "theme": c.theme, "status": c.status.value, "organization_id": str(c.organization_id) if c.organization_id else None, "opens_at": c.opens_at.isoformat() if c.opens_at else None, "closes_at": c.closes_at.isoformat() if c.closes_at else None, "evaluation_criteria": c.evaluation_criteria or DEFAULT_CRITERIA, "eligibility": c.eligibility, "prize_or_grant": c.prize_or_grant, "created_by": str(c.created_by), "created_at": c.created_at.isoformat(), "submission_count": sub_count, "is_demo": c.is_demo, "allowed_transitions": [s.value for s in CHALLENGE_TRANSITIONS.get(c.status, [])], "is_open": c.status == ChallengeStatus.OPEN and (c.closes_at is None or c.closes_at > _now())}


def _submission(db: Session, sid: uuid.UUID) -> Submission:
    s = db.scalar(select(Submission).options(selectinload(Submission.attachments), selectinload(Submission.evaluations), selectinload(Submission.pilots)).execution_options(populate_existing=True).where(Submission.id == sid))
    if not s:
        raise NotFoundError("Submission not found")
    return s


def _weighted_score(criteria: List[Dict[str, Any]], scores: Dict[str, float]) -> float:
    total_w = sum(float(c.get("weight", 1)) for c in criteria) or 1.0
    score = 0.0
    for c in criteria:
        val = float(scores.get(c["code"], 0))
        mx = float(c.get("max", 10)) or 10
        score += (val / mx) * float(c.get("weight", 1)) / total_w * 100
    return round(score, 2)


def _submission_dict(db: Session, s: Submission, viewer: Optional[User], perms: set, challenge: Optional[Challenge] = None) -> Dict[str, Any]:
    challenge = challenge or db.get(Challenge, s.challenge_id)
    reviewer = viewer is not None and (viewer.is_superuser or P.INNOVATION_EVALUATE in perms or P.INNOVATION_MANAGE in perms or (challenge and challenge.created_by == viewer.id))
    owner = viewer is not None and s.applicant_id == viewer.id
    criteria = (challenge.evaluation_criteria if challenge and challenge.evaluation_criteria else DEFAULT_CRITERIA)
    evals = [{"id": str(e.id), "evaluator_id": str(e.evaluator_id), "scores": e.scores, "weighted_score": e.total_score, "comments": e.comments if reviewer else None, "recommendation": e.recommendation, "created_at": e.created_at.isoformat()} for e in s.evaluations] if reviewer else []
    avg = round(sum(e.total_score or 0 for e in s.evaluations) / len(s.evaluations), 2) if s.evaluations else None
    out = {"id": str(s.id), "challenge_id": str(s.challenge_id), "title": s.title, "abstract": s.abstract, "team_name": s.team_name, "status": s.status, "submitted_by": str(s.applicant_id), "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None, "created_at": s.created_at.isoformat(), "is_demo": challenge.is_demo if challenge else False, "attachments": [{"id": str(a.id), "file_name": a.file_name, "mime_type": a.mime_type, "file_size": a.file_size} for a in s.attachments], "evaluation_count": len(s.evaluations), "average_score": avg if reviewer or owner else None, "criteria": criteria}
    if reviewer or owner:
        out.update({"proposal": s.proposal, "organization_id": str(s.organization_id) if s.organization_id else None, "contact_email": s.contact_email, "links": s.links, "evaluations": evals, "decision_note": s.decision_note, "pilots": [{"id": str(p.id), "title": p.title, "status": p.status, "start_date": p.start_date.isoformat() if p.start_date else None, "end_date": p.end_date.isoformat() if p.end_date else None} for p in s.pilots]})
    return out


# ---------------------------------------------------------------------------
# Portal overview
# ---------------------------------------------------------------------------
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    by_status = {s.value: (db.scalar(select(func.count(Challenge.id)).where(Challenge.status == s, Challenge.deleted_at.is_(None))) or 0) for s in ChallengeStatus}
    return {"challenges_by_status": by_status, "open_challenges": by_status.get("open", 0), "submissions_total": db.scalar(select(func.count(Submission.id)).where(Submission.status != "draft")) or 0, "pilots_active": db.scalar(select(func.count(Pilot.id)).where(Pilot.status.in_(["planned", "active"]))) or 0, "themes": [{"value": t, "count": c} for t, c in db.execute(select(Challenge.theme, func.count()).where(Challenge.theme.is_not(None), Challenge.deleted_at.is_(None)).group_by(Challenge.theme).order_by(func.count().desc())).all()], "default_criteria": DEFAULT_CRITERIA}


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------
@challenges_router.get("")
def list_challenges(page: PageParams = Depends(), q: Optional[str] = None, status_filter: Annotated[Optional[ChallengeStatus], Query(alias="status")] = None, theme: Optional[str] = None, challenge_type: Optional[str] = None, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    stmt = select(Challenge).where(Challenge.deleted_at.is_(None))
    if user is None:
        stmt = stmt.where(Challenge.status.in_(PUBLIC_STATUSES))
    elif not user.is_superuser:
        stmt = stmt.where(or_(Challenge.status.in_(PUBLIC_STATUSES), Challenge.created_by == user.id))
    if q:
        stmt = stmt.where(or_(Challenge.title.ilike(f"%{q}%"), Challenge.summary.ilike(f"%{q}%")))
    if status_filter:
        stmt = stmt.where(Challenge.status == status_filter)
    if theme:
        stmt = stmt.where(Challenge.theme.ilike(f"%{theme}%"))
    if challenge_type:
        stmt = stmt.where(Challenge.challenge_type == challenge_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Challenge.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([_challenge_dict(db, c, user) for c in rows], total, page.page, page.page_size)


@challenges_router.post("", status_code=status.HTTP_201_CREATED)
def create_challenge(payload: ChallengeCreate, request: Request, user: User = Depends(require_permissions(P.INNOVATION_CREATE, P.INNOVATION_MANAGE, any_of=True)), db: Session = Depends(get_db)):
    if payload.closes_at and payload.opens_at and payload.closes_at <= payload.opens_at:
        raise ValidationFailed("closes_at must be after opens_at")
    c = Challenge(**payload.model_dump(), slug=unique_slug(db, Challenge, payload.title), created_by=user.id)
    if not c.evaluation_criteria:
        c.evaluation_criteria = DEFAULT_CRITERIA
    db.add(c)
    db.flush()
    audit.record(db, "innovation.challenge_create", user=user, resource_type="challenge", resource_id=c.id, request=request)
    db.commit()
    indexer.index_challenge(db, c)
    return _challenge_dict(db, c, user)


@challenges_router.get("/{cid}")
def get_challenge(cid: uuid.UUID, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    c = _challenge(db, cid)
    if c.status not in PUBLIC_STATUSES and (user is None or not (user.is_superuser or c.created_by == user.id)):
        raise NotFoundError("Challenge not found")
    return _challenge_dict(db, c, user)


@challenges_router.patch("/{cid}")
def update_challenge(cid: uuid.UUID, payload: ChallengeUpdate, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    c = _challenge(db, cid)
    if not _can_manage(c, user, perms):
        raise ForbiddenError("You cannot manage this challenge")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    audit.record(db, "innovation.challenge_update", user=user, resource_type="challenge", resource_id=c.id, detail={"fields": list(changes)}, request=request)
    db.commit()
    indexer.index_challenge(db, c)
    return _challenge_dict(db, c, user)


@challenges_router.post("/{cid}/transition")
def transition_challenge(cid: uuid.UUID, payload: TransitionIn, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    c = _challenge(db, cid)
    if not _can_manage(c, user, perms):
        raise ForbiddenError("You cannot manage this challenge")
    if payload.status not in CHALLENGE_TRANSITIONS.get(c.status, []):
        raise ConflictError(f"Cannot move challenge from {c.status.value} to {payload.status.value}")
    if payload.status in (ChallengeStatus.PUBLISHED, ChallengeStatus.OPEN) and P.INNOVATION_MANAGE not in perms and not user.is_superuser:
        raise ForbiddenError("innovation.manage permission required to publish/open a challenge")
    old = c.status
    c.status = payload.status
    if payload.status == ChallengeStatus.OPEN and not c.opens_at:
        c.opens_at = _now()
    if payload.status == ChallengeStatus.SHORTLISTED:
        # auto-shortlist top submissions by average weighted score
        subs = db.scalars(select(Submission).options(selectinload(Submission.evaluations)).where(Submission.challenge_id == c.id, Submission.status == "under_evaluation")).all()
        scored = sorted([(sum(e.total_score or 0 for e in s.evaluations) / len(s.evaluations), s) for s in subs if s.evaluations], key=lambda t: -t[0])
        keep = max(1, int(round(len(scored) * 0.3))) if scored else 0
        for i, (score, s) in enumerate(scored):
            s.status = "shortlisted" if i < keep else "not_selected"
            notify(db, s.applicant_id, "innovation", f"Submission {s.status.replace('_', ' ')}", f"{s.title} — {c.title}", link=f"/app/innovation/submissions/{s.id}", email=True)
    audit.record(db, "innovation.challenge_transition", user=user, resource_type="challenge", resource_id=c.id, detail={"from": old.value, "to": payload.status.value, "note": payload.note}, request=request)
    db.commit()
    indexer.index_challenge(db, c)
    return _challenge_dict(db, c, user)


@challenges_router.get("/{cid}/submissions")
def challenge_submissions(cid: uuid.UUID, page: PageParams = Depends(), status_filter: Annotated[Optional[str], Query(alias="status")] = None, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    c = _challenge(db, cid)
    reviewer = user.is_superuser or P.INNOVATION_EVALUATE in perms or P.INNOVATION_MANAGE in perms or c.created_by == user.id
    stmt = select(Submission).options(selectinload(Submission.evaluations), selectinload(Submission.attachments), selectinload(Submission.pilots)).where(Submission.challenge_id == c.id)
    if not reviewer:
        stmt = stmt.where(Submission.applicant_id == user.id)
    else:
        stmt = stmt.where(Submission.status != "draft")
    if status_filter:
        stmt = stmt.where(Submission.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Submission.submitted_at.desc().nullslast()).offset(page.offset).limit(page.page_size)).all()
    return Page.build([_submission_dict(db, s, user, perms, c) for s in rows], total, page.page, page.page_size)


@challenges_router.post("/{cid}/submissions", status_code=status.HTTP_201_CREATED)
def create_submission(cid: uuid.UUID, payload: SubmissionCreate, request: Request, user: User = Depends(require_permissions(P.INNOVATION_SUBMIT)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    c = _challenge(db, cid)
    if c.status != ChallengeStatus.OPEN or (c.closes_at and c.closes_at < _now()):
        raise ConflictError("Challenge is not open for submissions")
    s = Submission(challenge_id=c.id, applicant_id=user.id, status="draft", **payload.model_dump())
    db.add(s)
    db.flush()
    audit.record(db, "innovation.submission_create", user=user, resource_type="submission", resource_id=s.id, request=request)
    db.commit()
    return _submission_dict(db, _submission(db, s.id), user, perms, c)


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
@submissions_router.get("/mine")
def my_submissions(user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    rows = db.scalars(select(Submission).options(selectinload(Submission.evaluations), selectinload(Submission.attachments), selectinload(Submission.pilots)).where(Submission.applicant_id == user.id).order_by(Submission.created_at.desc())).all()
    return {"items": [_submission_dict(db, s, user, perms) for s in rows]}


@submissions_router.get("/{sid}")
def get_submission(sid: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    c = db.get(Challenge, s.challenge_id)
    if s.applicant_id != user.id and not (user.is_superuser or P.INNOVATION_EVALUATE in perms or P.INNOVATION_MANAGE in perms or c.created_by == user.id):
        raise ForbiddenError("You cannot view this submission")
    return _submission_dict(db, s, user, perms, c)


@submissions_router.patch("/{sid}")
def update_submission(sid: uuid.UUID, payload: SubmissionCreate, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    if s.applicant_id != user.id:
        raise ForbiddenError("You can only edit your own submission")
    if s.status != "draft":
        raise ConflictError("Submitted proposals cannot be edited")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return _submission_dict(db, _submission(db, s.id), user, perms)


@submissions_router.post("/{sid}/attachments", status_code=status.HTTP_201_CREATED)
async def add_attachment(sid: uuid.UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    if s.applicant_id != user.id or s.status != "draft":
        raise ForbiddenError("Attachments can only be added to your own draft submission")
    if len(s.attachments) >= 10:
        raise ValidationFailed("Maximum 10 attachments")
    data = read_upload(file.file, settings.max_upload_mb)
    mime = validate_upload(data, file.filename or "upload", file.content_type)
    key = build_key(f"submissions/{s.id}", file.filename or "upload")
    get_storage().put(key, data, mime)
    a = SubmissionAttachment(submission_id=s.id, file_name=(file.filename or "upload")[:500], storage_key=key, mime_type=mime, file_size=len(data), checksum_sha256=sha256_bytes(data))
    db.add(a)
    db.commit()
    return {"id": str(a.id), "file_name": a.file_name, "mime_type": a.mime_type, "file_size": a.file_size}


@submissions_router.get("/{sid}/attachments/{aid}/download")
def download_attachment(sid: uuid.UUID, aid: uuid.UUID, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    c = db.get(Challenge, s.challenge_id)
    if s.applicant_id != user.id and not (user.is_superuser or P.INNOVATION_EVALUATE in perms or P.INNOVATION_MANAGE in perms or c.created_by == user.id):
        raise ForbiddenError("You cannot download this attachment")
    a = next((a for a in s.attachments if a.id == aid), None)
    if not a:
        raise NotFoundError("Attachment not found")
    return StreamingResponse(get_storage().stream(a.storage_key), media_type=a.mime_type, headers={"Content-Disposition": f'attachment; filename="{a.file_name}"'})


@submissions_router.post("/{sid}/submit")
def submit_submission(sid: uuid.UUID, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    if s.applicant_id != user.id:
        raise ForbiddenError("You can only submit your own proposal")
    if s.status != "draft":
        raise ConflictError("Already submitted")
    c = db.get(Challenge, s.challenge_id)
    if c.status != ChallengeStatus.OPEN or (c.closes_at and c.closes_at < _now()):
        raise ConflictError("Challenge is closed")
    if not (s.abstract or s.proposal):
        raise ValidationFailed("Provide an abstract or proposal before submitting")
    s.status = "submitted"
    s.submitted_at = _now()
    notify(db, c.created_by, "innovation", "New submission received", f"{s.title} — {c.title}", link=f"/app/innovation/challenges/{c.id}")
    audit.record(db, "innovation.submission_submit", user=user, resource_type="submission", resource_id=s.id, request=request)
    db.commit()
    return _submission_dict(db, s, user, perms, c)


@submissions_router.post("/{sid}/evaluate", status_code=status.HTTP_201_CREATED)
def evaluate(sid: uuid.UUID, payload: EvaluationIn, request: Request, user: User = Depends(require_permissions(P.INNOVATION_EVALUATE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    c = db.get(Challenge, s.challenge_id)
    if s.applicant_id == user.id:
        raise ForbiddenError("You cannot evaluate your own submission")
    if s.status not in ("submitted", "under_evaluation"):
        raise ConflictError(f"Submission in status {s.status} cannot be evaluated")
    criteria = c.evaluation_criteria or DEFAULT_CRITERIA
    codes = {cr["code"] for cr in criteria}
    unknown = set(payload.scores) - codes
    if unknown:
        raise ValidationFailed(f"Unknown criteria: {sorted(unknown)}; expected {sorted(codes)}")
    for cr in criteria:
        val = payload.scores.get(cr["code"])
        if val is None or val < 0 or val > float(cr.get("max", 10)):
            raise ValidationFailed(f"Score for {cr['code']} must be between 0 and {cr.get('max', 10)}")
    existing = next((e for e in s.evaluations if e.evaluator_id == user.id), None)
    weighted = _weighted_score(criteria, payload.scores)
    if existing:
        existing.scores, existing.comments, existing.recommendation, existing.total_score = payload.scores, payload.comments, payload.recommendation, weighted
    else:
        db.add(Evaluation(submission_id=s.id, evaluator_id=user.id, scores=payload.scores, total_score=weighted, comments=payload.comments, recommendation=payload.recommendation))
    s.status = "under_evaluation"
    db.flush()
    s.total_score = round(sum(e.total_score or 0 for e in s.evaluations) / len(s.evaluations), 2) if s.evaluations else weighted
    audit.record(db, "innovation.evaluate", user=user, resource_type="submission", resource_id=s.id, detail={"weighted_score": weighted, "recommendation": payload.recommendation}, request=request)
    db.commit()
    return _submission_dict(db, _submission(db, s.id), user, perms, c)


@submissions_router.post("/{sid}/decision")
def decide(sid: uuid.UUID, request: Request, decision: Annotated[str, Query(pattern="^(shortlist|not_selected|withdraw)$")], note: Optional[str] = None, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    c = db.get(Challenge, s.challenge_id)
    if decision == "withdraw":
        if s.applicant_id != user.id:
            raise ForbiddenError("Only the submitter can withdraw")
        s.status = "withdrawn"
    else:
        if not _can_manage(c, user, perms):
            raise ForbiddenError("You cannot decide on this submission")
        s.status = "shortlisted" if decision == "shortlist" else "not_selected"
        s.decision_note = note
        notify(db, s.applicant_id, "innovation", f"Submission {s.status.replace('_', ' ')}", f"{s.title} — {c.title}", link=f"/app/innovation/submissions/{s.id}", email=True)
    audit.record(db, f"innovation.submission_{decision}", user=user, resource_type="submission", resource_id=s.id, detail={"note": note}, request=request)
    db.commit()
    return _submission_dict(db, s, user, perms, c)


@submissions_router.post("/{sid}/pilots", status_code=status.HTTP_201_CREATED)
def create_pilot(sid: uuid.UUID, payload: PilotIn, request: Request, user: User = Depends(require_permissions(P.INNOVATION_MANAGE)), db: Session = Depends(get_db)):
    s = _submission(db, sid)
    if s.status != "shortlisted":
        raise ConflictError("Only shortlisted submissions can move to pilot")
    p = Pilot(submission_id=s.id, challenge_id=s.challenge_id, manager_id=user.id, status="planned", **payload.model_dump())
    db.add(p)
    s.status = "pilot"
    c = db.get(Challenge, s.challenge_id)
    if c.status in (ChallengeStatus.SHORTLISTED, ChallengeStatus.EVALUATION):
        c.status = ChallengeStatus.PILOT
    notify(db, s.applicant_id, "innovation", "Pilot initiated", payload.title, link=f"/app/innovation/submissions/{s.id}", email=True)
    audit.record(db, "innovation.pilot_create", user=user, resource_type="pilot", resource_id=p.id, request=request)
    db.commit()
    return {"id": str(p.id), "title": p.title, "status": p.status, "submission_id": str(s.id)}


@router.get("/pilots")
def list_pilots(status_filter: Annotated[Optional[str], Query(alias="status")] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Pilot)
    if status_filter:
        stmt = stmt.where(Pilot.status == status_filter)
    rows = db.scalars(stmt.order_by(Pilot.created_at.desc()).limit(200)).all()
    return {"items": [{"id": str(p.id), "title": p.title, "description": p.description, "status": p.status, "submission_id": str(p.submission_id), "challenge_id": str(p.challenge_id), "admin_unit_id": str(p.admin_unit_id) if p.admin_unit_id else None, "start_date": p.start_date.isoformat() if p.start_date else None, "end_date": p.end_date.isoformat() if p.end_date else None, "budget": p.budget, "kpis": p.kpis, "outcomes": p.outcome_summary, "manager_id": str(p.manager_id) if p.manager_id else None, "is_demo": p.is_demo} for p in rows]}


@router.patch("/pilots/{pid}")
def update_pilot(pid: uuid.UUID, status_value: Annotated[Optional[str], Query(alias="status", pattern="^(planned|active|completed|cancelled)$")] = None, outcomes: Optional[str] = None, user: User = Depends(require_permissions(P.INNOVATION_MANAGE)), db: Session = Depends(get_db)):
    p = db.get(Pilot, pid)
    if not p:
        raise NotFoundError("Pilot not found")
    if status_value:
        p.status = status_value
    if outcomes is not None:
        p.outcome_summary = outcomes
    db.commit()
    return {"id": str(p.id), "status": p.status, "outcomes": p.outcome_summary}
