from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, redact, request_id_ctx
from app.models.identity import User
from app.models.platform import AuditLog

logger = get_logger("bhoomitra.audit")


def _ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    from app.core.middleware import client_ip

    return client_ip(request)


def record(
    db: Session,
    action: str,
    *,
    user: Optional[User] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    result: str = "success",
    detail: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    organization_id: Optional[uuid.UUID] = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        organization_id=organization_id or (user.primary_organization_id if user else None),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        result=result,
        request_id=request_id_ctx.get() if request_id_ctx.get() != "-" else None,
        ip_address=_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
        detail=redact(detail) if detail else None,
    )
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()
    logger.info("audit", extra={"extra_data": {"action": action, "resource": f"{resource_type}:{resource_id}", "result": result}})
    return entry


def search(db: Session, *, action: Optional[str] = None, user_id: Optional[uuid.UUID] = None, resource_type: Optional[str] = None, resource_id: Optional[str] = None, result: Optional[str] = None, offset: int = 0, limit: int = 50):
    stmt = select(AuditLog)
    count_stmt = select(func.count(AuditLog.id))
    conds = []
    if action:
        conds.append(AuditLog.action.ilike(f"{action}%"))
    if user_id:
        conds.append(AuditLog.user_id == user_id)
    if resource_type:
        conds.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conds.append(AuditLog.resource_id == resource_id)
    if result:
        conds.append(AuditLog.result == result)
    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)).all()
    return rows, total
