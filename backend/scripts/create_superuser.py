#!/usr/bin/env python3
"""Create or promote a super administrator.

Usage: python scripts/create_superuser.py --email admin@example.org --name "Admin" --password 'Str0ngPassw0rd!'
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.permissions import Roles  # noqa: E402
from app.core.security import hash_password, validate_password_strength  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.identity import User, UserStatus  # noqa: E402
from app.seed.bootstrap import seed_permissions_and_roles  # noqa: E402
from app.services.auth_service import assign_role  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", required=True)
    a = p.parse_args()
    problem = validate_password_strength(a.password)
    if problem:
        raise SystemExit(problem)
    db = SessionLocal()
    try:
        seed_permissions_and_roles(db)
        u = db.scalar(select(User).where(User.email == a.email.lower()))
        if u:
            u.password_hash = hash_password(a.password)
            u.password_changed_at = datetime.now(timezone.utc)
        else:
            u = User(email=a.email.lower(), full_name=a.name, password_hash=hash_password(a.password), status=UserStatus.ACTIVE, password_changed_at=datetime.now(timezone.utc))
            db.add(u)
            db.flush()
        u.is_superuser = True
        u.status = UserStatus.ACTIVE
        assign_role(db, u, Roles.SUPER_ADMIN)
        db.commit()
        print(f"super administrator ready: {u.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
