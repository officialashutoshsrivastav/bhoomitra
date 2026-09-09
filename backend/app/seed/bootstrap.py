from __future__ import annotations

from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.permissions import ALL_PERMISSIONS, PERMISSION_DESCRIPTIONS, ROLE_LABELS, ROLE_PERMISSIONS, Roles
from app.core.security import hash_password
from app.models.identity import Organization, Permission, Role, RolePermission, User, UserRole, UserStatus
from app.models.platform import IntegrationConfig

logger = get_logger("bhoomitra.seed")


def seed_permissions_and_roles(db: Session) -> Dict[str, Role]:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code in ALL_PERMISSIONS:
        if code not in existing:
            p = Permission(code=code, description=PERMISSION_DESCRIPTIONS.get(code))
            db.add(p)
            existing[code] = p
    db.flush()

    roles = {r.name: r for r in db.scalars(select(Role)).all()}
    for name, perms in ROLE_PERMISSIONS.items():
        role = roles.get(name)
        if not role:
            role = Role(name=name, label=ROLE_LABELS[name], description=f"System role: {ROLE_LABELS[name]}", is_system=True)
            db.add(role)
            db.flush()
            roles[name] = role
        current = {rp.permission_id for rp in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id)).all()}
        for code in perms:
            pid = existing[code].id
            if pid not in current:
                db.add(RolePermission(role_id=role.id, permission_id=pid))
    db.flush()
    return roles


def seed_default_organization(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == "dolr-mord"))
    if not org:
        org = Organization(
            name="Department of Land Resources, Ministry of Rural Development",
            slug="dolr-mord",
            org_type="government",
            description="PME Division — Department of Land Resources, Ministry of Rural Development, Government of India",
            website="https://dolr.gov.in",
            state="National",
        )
        db.add(org)
        db.flush()
    return org


def seed_superadmin(db: Session, roles: Dict[str, Role]) -> User | None:
    email = settings.bootstrap_superadmin_email
    password = settings.bootstrap_superadmin_password
    if not email or not password:
        return None
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user:
        return user
    org = seed_default_organization(db)
    user = User(email=email.lower(), full_name="Platform Super Administrator", password_hash=hash_password(password), status=UserStatus.ACTIVE, is_superuser=True, primary_organization_id=org.id, designation="Super Administrator")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=roles[Roles.SUPER_ADMIN].id))
    db.flush()
    logger.info("bootstrap superadmin created", extra={"extra_data": {"email": email}})
    return user


CONNECTORS = [
    ("geoboundaries", "geoBoundaries administrative boundaries (CC BY 4.0)", "boundaries"),
    ("datagov_in", "data.gov.in Open Government Data API", "datasets"),
    ("stac_satellite", "STAC satellite catalogue (Sentinel-2 / Landsat)", "satellite"),
    ("opensearch", "OpenSearch full-text index", "search"),
    ("object_storage", "S3 / MinIO object storage", "storage"),
    ("openai", "OpenAI API (LLM + embeddings)", "ai"),
    ("email", "Email delivery (SMTP)", "notifications"),
]


def seed_integrations(db: Session) -> None:
    existing = {i.connector for i in db.scalars(select(IntegrationConfig)).all()}
    for connector, name, kind in CONNECTORS:
        if connector not in existing:
            db.add(IntegrationConfig(connector=connector, display_name=name, kind=kind, enabled=False, mode="demo"))
    db.flush()


def bootstrap(db: Session) -> None:
    roles = seed_permissions_and_roles(db)
    seed_default_organization(db)
    seed_superadmin(db, roles)
    seed_integrations(db)
    db.commit()
