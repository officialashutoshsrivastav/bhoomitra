from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.identity import User
from app.notifications import service as notifications
from app.schemas.common import Message

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(unread_only: bool = False, limit: Annotated[int, Query(le=200)] = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items, total, unread = notifications.list_for_user(db, user.id, unread_only, 0, limit)
    return {"unread": unread, "total": total, "items": [{"id": str(n.id), "category": n.category, "title": n.title, "body": n.body, "link": n.link, "read_at": n.read_at.isoformat() if n.read_at else None, "created_at": n.created_at.isoformat()} for n in items]}


@router.post("/read", response_model=Message)
def mark_read(notification_id: Optional[uuid.UUID] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = notifications.mark_read(db, user.id, [notification_id] if notification_id else None)
    db.commit()
    return Message(message=f"{n} notification(s) marked read")
