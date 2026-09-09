from __future__ import annotations

import smtplib
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.identity import User
from app.models.platform import Notification

logger = get_logger("bhoomitra.notifications")


class EmailProvider(ABC):
    name = "abstract"

    @abstractmethod
    def send(self, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> Tuple[bool, str]: ...


class ConsoleEmail(EmailProvider):
    name = "console"

    def send(self, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> Tuple[bool, str]:
        logger.info("email", extra={"extra_data": {"to": to, "subject": subject, "preview": body_text[:120]}})
        return True, "logged"


class SMTPEmail(EmailProvider):
    name = "smtp"

    def send(self, to: str, subject: str, body_text: str, body_html: Optional[str] = None) -> Tuple[bool, str]:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password or "")
                s.send_message(msg)
            return True, "sent"
        except Exception as exc:
            logger.warning("email send failed", extra={"extra_data": {"to": to, "error": str(exc)}})
            return False, str(exc)


def get_email_provider() -> EmailProvider:
    if settings.email_backend == "smtp" and settings.smtp_host:
        return SMTPEmail()
    return ConsoleEmail()


def notify(
    db: Session,
    user: User | uuid.UUID,
    category: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    email: bool = False,
) -> Notification:
    user_id = user.id if isinstance(user, User) else user
    n = Notification(user_id=user_id, category=category, title=title, body=body, link=link, channel="email" if email else "in_app")
    db.add(n)
    db.flush()
    if email:
        target = db.get(User, user_id) if not isinstance(user, User) else user
        if target:
            ok, msg = get_email_provider().send(target.email, f"[Bhoomitra] {title}", body or title)
            n.email_status = "sent" if ok else f"failed:{msg[:40]}"
    return n


def notify_many(db: Session, user_ids: Iterable[uuid.UUID], category: str, title: str, body: Optional[str] = None, link: Optional[str] = None) -> int:
    count = 0
    for uid in set(user_ids):
        notify(db, uid, category, title, body, link)
        count += 1
    return count


def list_for_user(db: Session, user_id: uuid.UUID, unread_only: bool = False, offset: int = 0, limit: int = 50) -> Tuple[List[Notification], int, int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.read_at.is_(None))) or 0
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)).all()
    return rows, total, unread


def mark_read(db: Session, user_id: uuid.UUID, notification_ids: Optional[List[uuid.UUID]] = None) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if notification_ids:
        stmt = stmt.where(Notification.id.in_(notification_ids))
    res = db.execute(stmt.values(read_at=datetime.now(timezone.utc)))
    return res.rowcount or 0
