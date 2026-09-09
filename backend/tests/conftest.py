"""Test fixtures — run against a real PostgreSQL/PostGIS/pgvector database.

The schema is created with the Alembic migrations (downgrade base → upgrade head)
so the migrations themselves are exercised on every run.
"""
from __future__ import annotations

import os
import tempfile
import uuid

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://bhoomitra:bhoomitra_dev_password@localhost:5432/bhoomitra_test")
os.environ["TASK_EXECUTION_MODE"] = "inline"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_PATH"] = tempfile.mkdtemp(prefix="bhoomitra-test-storage-")
os.environ["LOG_JSON"] = "false"
os.environ["EMAIL_BACKEND"] = "console"
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-0123456789abcdef0123456789")
os.environ.setdefault("BOOTSTRAP_SUPERADMIN_EMAIL", "admin@test.bhoomitra.in")
os.environ.setdefault("BOOTSTRAP_SUPERADMIN_PASSWORD", "Admin@Test2026x")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def database():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from app.db.database import SessionLocal
    from app.seed.bootstrap import bootstrap

    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db_session():
    from app.db.database import SessionLocal

    db = SessionLocal()
    yield db
    db.close()


def _login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    from app.core.config import settings

    return _login(client, settings.bootstrap_superadmin_email, settings.bootstrap_superadmin_password)


@pytest.fixture(scope="session")
def make_user(client, admin_headers):
    """Factory: create an active user with the given roles; returns (headers, user dict)."""
    def _make(roles, password: str = "Passw0rd!Strong", org_id=None):
        email = f"user-{uuid.uuid4().hex[:10]}@test.bhoomitra.in"
        r = client.post("/api/v1/admin/users", json={"email": email, "full_name": f"Test {roles[0]}", "password": password, "roles": roles, "organization_id": org_id}, headers=admin_headers)
        assert r.status_code == 201, r.text
        return _login(client, email, password), r.json()

    return _make


@pytest.fixture(scope="session")
def researcher(make_user):
    return make_user(["researcher"])


@pytest.fixture(scope="session")
def official(make_user):
    return make_user(["government_official"])


@pytest.fixture(scope="session")
def policy_maker(make_user):
    return make_user(["policy_maker"])


@pytest.fixture(scope="session")
def gis_analyst(make_user):
    return make_user(["gis_analyst"])


@pytest.fixture(scope="session")
def public_user(make_user):
    return make_user(["public_user"])


def square(x0: float, y0: float, w: float, h: float) -> dict:
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


@pytest.fixture(scope="session")
def demo_geography(db_session):
    """Two demo districts inside one state plus a land-use layer with 40 parcels."""
    import json
    import random

    from sqlalchemy import func, select

    from app.gis.service import add_features, refresh_unit_metrics
    from app.models.gis import AdminLevel, AdminUnit, GISLayer, LayerCategory

    db = db_session
    st = db.scalar(select(AdminUnit).where(AdminUnit.code == "T-ST"))
    if not st:
        def g(poly):
            return func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(poly)), 4326))

        st = AdminUnit(name="Test State", code="T-ST", level=AdminLevel.STATE, geom=g(square(76.0, 30.0, 2.0, 2.0)), source="test", is_demo=True)
        db.add(st)
        db.flush()
        d1 = AdminUnit(name="Test District A", code="T-D-A", level=AdminLevel.DISTRICT, parent_id=st.id, geom=g(square(76.0, 30.0, 1.0, 2.0)), source="test", is_demo=True)
        d2 = AdminUnit(name="Test District B", code="T-D-B", level=AdminLevel.DISTRICT, parent_id=st.id, geom=g(square(77.0, 30.0, 1.0, 2.0)), source="test", is_demo=True)
        db.add_all([d1, d2])
        db.flush()
        for u in (st, d1, d2):
            refresh_unit_metrics(db, u)
        layer = GISLayer(name="Test Land Use", slug="test-land-use", category=LayerCategory.LAND_USE, geometry_type="Polygon", class_field="lulc", value_field="score", is_public=True, is_demo=True, source="test")
        db.add(layer)
        db.flush()
        rng = random.Random(1)
        classes = ["cropland", "forest", "built_up", "water", "wasteland", "grassland"]
        feats = []
        for i in range(40):
            x, y = 76.0 + rng.random() * 1.9, 30.0 + rng.random() * 1.9
            feats.append({"type": "Feature", "geometry": square(x, y, 0.08, 0.08), "properties": {"lulc": classes[i % 6], "score": rng.random() * 100, "name": f"parcel-{i}", "valid_from": "2023-01-01"}})
        add_features(db, layer, {"type": "FeatureCollection", "features": feats}, is_demo=True)
        db.commit()
    else:
        d1 = db.scalar(select(AdminUnit).where(AdminUnit.code == "T-D-A"))
        d2 = db.scalar(select(AdminUnit).where(AdminUnit.code == "T-D-B"))
        layer = db.scalar(select(GISLayer).where(GISLayer.slug == "test-land-use"))
    return {"state": st, "d1": d1, "d2": d2, "layer": layer}


@pytest.fixture(scope="session")
def published_document(client, researcher, official):
    """A published, public document with processed text (chunks + embeddings)."""
    rh, _ = researcher
    oh, _ = official
    r = client.post("/api/v1/documents", json={"title": "Test Land Records Modernisation Review", "document_type": "government_report", "description": "Review of record digitisation", "keywords": ["land records"], "topic": "land records", "geography": "Test State", "publication_date": "2023-06-01", "visibility": "public", "language": "en"}, headers=rh)
    assert r.status_code == 201, r.text
    doc = r.json()
    text = ("The Digital India Land Records Modernisation Programme aims to computerise land records across all states.\n\n"
            "In Test State, 98 percent of cadastral maps were digitised by March 2023.\n\n"
            "Survey and resurvey using drones reduced boundary disputes by 22 percent in pilot districts.\n\n"
            "Integration of textual and spatial records remains a challenge in several districts due to legacy formats.\n\n"
            "Groundwater recharge structures built under watershed programmes raised post-monsoon water tables by 1.6 metres.\n\n")
    r = client.post(f"/api/v1/documents/{doc['id']}/versions", files={"file": ("review.txt", (text * 3).encode(), "text/plain")}, data={"change_note": "initial"}, headers=rh)
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["processing_status"] == "READY"
    r = client.post(f"/api/v1/documents/{doc['id']}/submit", headers=rh)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "approve", "comments": "ok"}, headers=oh)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/documents/{doc['id']}/publish", headers=oh)
    assert r.status_code == 200, r.text
    return {"doc": r.json(), "version": version}
