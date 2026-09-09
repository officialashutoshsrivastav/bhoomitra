"""Demo / Synthetic Data seeder.

Everything created here is flagged ``is_demo=True`` (or carries "Demo" in its
name) and must be badged as such in every interface. Boundaries are synthetic
cells, not real administrative boundaries. Run ``python scripts/seed.py``.
"""
from __future__ import annotations

import io
import json
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.permissions import Roles
from app.core.security import hash_password
from app.gis.service import add_features, refresh_unit_metrics
from app.ingestion import pipeline
from app.models.datasets import DataSource, Dataset, DatasetCategory, DatasetStatus
from app.models.gis import AdminLevel, AdminUnit, GISLayer, LayerCategory
from app.models.identity import Organization, SystemSetting, User, UserStatus
from app.models.intelligence import ScenarioStatus
from app.models.knowledge import Document, DocumentStatus, DocumentType, Policy, PolicyIndicator, PolicyStatus, ResearchOutput, ResearchProject, ResearchStatus, Visibility
from app.models.platform import Challenge, ChallengeStatus, Comment, Evaluation, Pilot, Submission, Task, Workspace, WorkspaceMember, WorkspaceResource, WorkspaceStatus
from app.schemas.datasets import DatasetCreate, DatasetVariableIn
from app.schemas.knowledge import DocumentCreate
from app.seed.bootstrap import seed_permissions_and_roles
from app.seed.demo_documents import DEMO_DOCUMENTS, _HEADER
from app.services import auth_service, dataset_service, document_service
from app.services.document_service import unique_slug
from app.simulation import engine as sim

logger = get_logger("bhoomitra.seed.demo")
DEMO_PASSWORD = "Demo@Bhoomitra2026"
SEED_MARKER = "demo.seeded_at"

DEMO_USERS = [
    ("platform.admin@demo.bhoomitra.in", "Priya Platform (Demo)", Roles.PLATFORM_ADMIN, "Platform Administrator"),
    ("official@demo.bhoomitra.in", "Arun Official (Demo)", Roles.GOVERNMENT_OFFICIAL, "Deputy Secretary, DoLR"),
    ("policy.maker@demo.bhoomitra.in", "Meera Policy (Demo)", Roles.POLICY_MAKER, "Joint Secretary, PME Division"),
    ("researcher@demo.bhoomitra.in", "Rahul Researcher (Demo)", Roles.RESEARCHER, "Senior Research Fellow"),
    ("academic@demo.bhoomitra.in", "Anita Academic (Demo)", Roles.ACADEMIC, "Associate Professor"),
    ("research.org@demo.bhoomitra.in", "Vikram Institute (Demo)", Roles.RESEARCH_ORG, "Programme Lead"),
    ("gis.analyst@demo.bhoomitra.in", "Geeta GIS (Demo)", Roles.GIS_ANALYST, "GIS Analyst"),
    ("data.analyst@demo.bhoomitra.in", "Dev Data (Demo)", Roles.DATA_ANALYST, "Data Analyst"),
    ("project.manager@demo.bhoomitra.in", "Pooja Projects (Demo)", Roles.PROJECT_MANAGER, "Project Manager"),
    ("evaluator@demo.bhoomitra.in", "Eshan Evaluator (Demo)", Roles.INNOVATION_EVALUATOR, "Innovation Evaluator"),
    ("expert@demo.bhoomitra.in", "Iqbal Expert (Demo)", Roles.EXPERT, "Industry Expert"),
    ("public@demo.bhoomitra.in", "Pat Public (Demo)", Roles.PUBLIC, "Citizen"),
]

STATE_NAMES = ["Demo State 1", "Demo State 2", "Demo State 3", "Demo State 4", "Demo State 5", "Demo State 6"]
LAND_CLASSES = ["cropland", "forest", "grassland", "built_up", "water", "wasteland"]
CLASS_WEIGHTS = [0.42, 0.18, 0.12, 0.10, 0.06, 0.12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def already_seeded(db: Session) -> bool:
    return db.scalar(select(SystemSetting.id).where(SystemSetting.key == SEED_MARKER)) is not None


# ---------------------------------------------------------------------------
# Geometry helpers — synthetic, non-overlapping cells with jittered corners
# ---------------------------------------------------------------------------
def _grid_points(rng: random.Random, cols: int, rows: int, x0: float, y0: float, w: float, h: float, jitter: float) -> List[List[Tuple[float, float]]]:
    pts = []
    for j in range(rows + 1):
        row = []
        for i in range(cols + 1):
            jx = rng.uniform(-jitter, jitter) if 0 < i < cols else 0.0
            jy = rng.uniform(-jitter, jitter) if 0 < j < rows else 0.0
            row.append((round(x0 + i * w + jx, 5), round(y0 + j * h + jy, 5)))
        pts.append(row)
    return pts


def _cell_polygon(pts, i, j) -> Dict[str, Any]:
    p00, p10, p11, p01 = pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i]
    return {"type": "Polygon", "coordinates": [[list(p00), list(p10), list(p11), list(p01), list(p00)]]}


def _bilinear(p00, p10, p11, p01, u, v):
    x = (1 - u) * (1 - v) * p00[0] + u * (1 - v) * p10[0] + u * v * p11[0] + (1 - u) * v * p01[0]
    y = (1 - u) * (1 - v) * p00[1] + u * (1 - v) * p10[1] + u * v * p11[1] + (1 - u) * v * p01[1]
    return (round(x, 5), round(y, 5))


def _subdivide(pts, i, j, rng: random.Random) -> List[Dict[str, Any]]:
    """Split one state cell into 2x2 district quads sharing a jittered centre."""
    p00, p10, p11, p01 = pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i]
    cu, cv = rng.uniform(0.4, 0.6), rng.uniform(0.4, 0.6)
    m = _bilinear(p00, p10, p11, p01, cu, cv)
    b = _bilinear(p00, p10, p11, p01, cu, 0)
    t = _bilinear(p00, p10, p11, p01, cu, 1)
    l = _bilinear(p00, p10, p11, p01, 0, cv)
    r = _bilinear(p00, p10, p11, p01, 1, cv)
    quads = [(p00, b, m, l), (b, p10, r, m), (l, m, t, p01), (m, r, p11, t)]
    return [{"type": "Polygon", "coordinates": [[list(a), list(bb), list(c), list(d), list(a)]]} for a, bb, c, d in quads]


def _geom(geojson: Dict[str, Any]):
    return func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326))


def _poly_bbox(poly: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in poly["coordinates"][0]]
    ys = [p[1] for p in poly["coordinates"][0]]
    return min(xs), min(ys), max(xs), max(ys)


def _random_blob(rng: random.Random, cx: float, cy: float, r: float, n: int = 7) -> Dict[str, Any]:
    import math

    pts = []
    for k in range(n):
        ang = 2 * math.pi * k / n
        rad = r * rng.uniform(0.6, 1.0)
        pts.append([round(cx + rad * math.cos(ang), 5), round(cy + rad * math.sin(ang) * 0.85, 5)])
    pts.append(pts[0])
    return {"type": "Polygon", "coordinates": [pts]}


# ---------------------------------------------------------------------------
# Seed steps
# ---------------------------------------------------------------------------
def seed_organizations(db: Session) -> Dict[str, Organization]:
    specs = [
        ("Department of Land Resources (Demo)", "dolr-demo", "ministry", "Demo entry mirroring DoLR, MoRD"),
        ("National Institute of Rural Development (Demo)", "nird-demo", "research_institute", "Demo research institute"),
        ("Demo State University", "demo-state-university", "university", "Demo academic partner"),
        ("Demo State 1 Revenue Department", "demo-state-1-revenue", "state_department", "Demo state revenue department"),
        ("GeoInnovate Labs (Demo)", "geoinnovate-demo", "industry", "Demo geospatial start-up"),
        ("Land Rights Collective (Demo)", "land-rights-collective-demo", "ngo", "Demo civil society organisation"),
    ]
    out = {}
    for name, slug, org_type, desc in specs:
        o = db.scalar(select(Organization).where(Organization.slug == slug))
        if not o:
            o = Organization(name=name, slug=slug, org_type=org_type, description=desc)
            db.add(o)
            db.flush()
        out[slug] = o
    db.commit()
    return out


def seed_users(db: Session, orgs: Dict[str, Organization]) -> Dict[str, User]:
    seed_permissions_and_roles(db)
    org_for_role = {Roles.PLATFORM_ADMIN: "dolr-demo", Roles.GOVERNMENT_OFFICIAL: "dolr-demo", Roles.POLICY_MAKER: "dolr-demo", Roles.RESEARCHER: "nird-demo", Roles.ACADEMIC: "demo-state-university", Roles.RESEARCH_ORG: "nird-demo", Roles.GIS_ANALYST: "demo-state-1-revenue", Roles.DATA_ANALYST: "dolr-demo", Roles.PROJECT_MANAGER: "dolr-demo", Roles.INNOVATION_EVALUATOR: "nird-demo", Roles.EXPERT: "geoinnovate-demo", Roles.PUBLIC: None}
    out = {}
    pw = hash_password(DEMO_PASSWORD)
    for email, name, role, designation in DEMO_USERS:
        u = db.scalar(select(User).where(User.email == email))
        if not u:
            org = org_for_role.get(role)
            u = User(email=email, full_name=name, password_hash=pw, status=UserStatus.ACTIVE, designation=designation, primary_organization_id=orgs[org].id if org else None, password_changed_at=_now())
            db.add(u)
            db.flush()
            auth_service.assign_role(db, u, role)
        out[role] = u
    db.commit()
    return out


def seed_admin_units(db: Session, rng: random.Random) -> Dict[str, List[AdminUnit]]:
    existing = db.scalar(select(AdminUnit).where(AdminUnit.code == "DEMO-IN"))
    if existing:
        states = db.scalars(select(AdminUnit).where(AdminUnit.level == AdminLevel.STATE, AdminUnit.is_demo.is_(True))).all()
        districts = db.scalars(select(AdminUnit).where(AdminUnit.level == AdminLevel.DISTRICT, AdminUnit.is_demo.is_(True))).all()
        return {"states": states, "districts": districts}
    cols, rows = 3, 2
    x0, y0, w, h = 74.0, 21.0, 2.4, 2.2
    pts = _grid_points(rng, cols, rows, x0, y0, w, h, jitter=0.35)
    country_poly = {"type": "Polygon", "coordinates": [[list(pts[0][0]), list(pts[0][cols]), list(pts[rows][cols]), list(pts[rows][0]), list(pts[0][0])]]}
    country = AdminUnit(name="Demo Country Extent", code="DEMO-IN", level=AdminLevel.COUNTRY, geom=_geom(country_poly), source="demo", source_license="synthetic", is_demo=True)
    db.add(country)
    db.flush()
    states, districts = [], []
    k = 0
    for j in range(rows):
        for i in range(cols):
            name = STATE_NAMES[k]
            st = AdminUnit(name=name, code=f"DEMO-ST-{k + 1}", level=AdminLevel.STATE, parent_id=country.id, geom=_geom(_cell_polygon(pts, i, j)), source="demo", source_license="synthetic", is_demo=True)
            db.add(st)
            db.flush()
            states.append(st)
            for d, poly in enumerate(_subdivide(pts, i, j, rng)):
                dist = AdminUnit(name=f"Demo District {k + 1}{'ABCD'[d]}", code=f"DEMO-D-{k + 1}{'ABCD'[d]}", level=AdminLevel.DISTRICT, parent_id=st.id, geom=_geom(poly), source="demo", source_license="synthetic", is_demo=True)
                db.add(dist)
                db.flush()
                districts.append(dist)
            k += 1
    db.flush()
    for u in [country] + states + districts:
        refresh_unit_metrics(db, u)
    db.commit()
    return {"states": states, "districts": districts}


def seed_layers(db: Session, rng: random.Random, units: Dict[str, List[AdminUnit]], owner: User) -> Dict[str, GISLayer]:
    layers: Dict[str, GISLayer] = {}
    specs = [
        ("Land Use Land Cover 2015 (Demo)", "land_use", "Polygon", "lulc", "confidence", {"cropland": "#c7d66b", "forest": "#1f7a3d", "grassland": "#9fd18a", "built_up": "#b0413e", "water": "#3b82c4", "wasteland": "#c9a36b"}, date(2015, 1, 1), date(2015, 12, 31)),
        ("Land Use Land Cover 2019 (Demo)", "land_use", "Polygon", "lulc", "confidence", {"cropland": "#c7d66b", "forest": "#1f7a3d", "grassland": "#9fd18a", "built_up": "#b0413e", "water": "#3b82c4", "wasteland": "#c9a36b"}, date(2019, 1, 1), date(2019, 12, 31)),
        ("Land Use Land Cover 2023 (Demo)", "land_use", "Polygon", "lulc", "confidence", {"cropland": "#c7d66b", "forest": "#1f7a3d", "grassland": "#9fd18a", "built_up": "#b0413e", "water": "#3b82c4", "wasteland": "#c9a36b"}, date(2023, 1, 1), date(2023, 12, 31)),
        ("Water Bodies (Demo)", "water", "Polygon", "type", "area_ha", {"pond": "#7cc4f5", "reservoir": "#2b6cb0", "wetland": "#5fa8a0"}, None, None),
        ("Forest Cover Density (Demo)", "forest", "Polygon", "density_class", "canopy_pct", {"very_dense": "#0b4d2a", "moderately_dense": "#2e8b57", "open": "#8fbc8f"}, None, None),
        ("Soil Erosion Risk (Demo)", "soil", "Polygon", "risk", "soil_loss_t_ha", {"low": "#e8f5e9", "moderate": "#ffe082", "high": "#ff8a65", "severe": "#c62828"}, None, None),
        ("Groundwater Observation Wells (Demo)", "water", "Point", "trend", "depth_m_bgl", {"declining": "#c62828", "stable": "#fbc02d", "rising": "#2e7d32"}, None, None),
        ("Flood Hazard Zones (Demo)", "climate_risk", "Polygon", "zone", "return_period_years", {"A": "#b71c1c", "B": "#f57c00", "C": "#fdd835"}, None, None),
        ("Watershed Development Projects (Demo)", "projects", "Point", "status", "treated_area_ha", {"completed": "#2e7d32", "ongoing": "#1976d2", "planned": "#9e9e9e"}, None, None),
        ("Wasteland Parcels (Demo)", "land_use", "Polygon", "category", "reclamation_priority", {"scrub": "#c9a36b", "gullied": "#a1887f", "salt_affected": "#e0e0e0", "waterlogged": "#80cbc4"}, None, None),
    ]
    for name, cat, gtype, class_field, value_field, legend, ts, te in specs:
        slug = unique_slug(db, GISLayer, name)
        existing = db.scalar(select(GISLayer).where(GISLayer.name == name))
        if existing:
            layers[name] = existing
            continue
        layer = GISLayer(name=name, slug=slug, description=f"{name}: synthetic features generated for demonstration.", category=LayerCategory(cat), geometry_type=gtype, class_field=class_field, value_field=value_field, legend=legend, style={"opacity": 0.75}, temporal_start=ts, temporal_end=te, source="Demo / Synthetic Data", source_license="synthetic", is_public=True, is_demo=True, created_by=owner.id)
        db.add(layer)
        db.flush()
        layers[name] = layer
    db.flush()
    districts = units["districts"]
    bboxes = {}
    for d in districts:
        gj = json.loads(db.scalar(select(func.ST_AsGeoJSON(AdminUnit.geom)).where(AdminUnit.id == d.id)))
        poly = gj["coordinates"][0] if gj["type"] == "Polygon" else gj["coordinates"][0][0]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        bboxes[d.id] = (min(xs), min(ys), max(xs), max(ys))

    def rnd_point(d):
        x0, y0, x1, y1 = bboxes[d.id]
        return rng.uniform(x0 + 0.05, x1 - 0.05), rng.uniform(y0 + 0.05, y1 - 0.05)

    # LULC parcels: same parcel grid across years with drift towards built-up
    parcels = []
    for d in districts:
        for _ in range(14):
            cx, cy = rnd_point(d)
            cls = rng.choices(LAND_CLASSES, CLASS_WEIGHTS)[0]
            parcels.append((cx, cy, rng.uniform(0.05, 0.11), cls))
    for name, year in (("Land Use Land Cover 2015 (Demo)", 2015), ("Land Use Land Cover 2019 (Demo)", 2019), ("Land Use Land Cover 2023 (Demo)", 2023)):
        if layers[name].feature_count:
            continue
        feats = []
        for idx, (cx, cy, r, cls) in enumerate(parcels):
            c = cls
            drift = rng.random()
            if year >= 2019 and cls in ("cropland", "grassland") and drift < 0.06:
                c = "built_up"
            if year >= 2023 and cls in ("cropland", "grassland") and drift < 0.11:
                c = "built_up"
            if year >= 2019 and cls == "wasteland" and 0.4 < drift < 0.55:
                c = "forest"
            feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, r), "properties": {"lulc": c, "confidence": round(rng.uniform(0.7, 0.98), 2), "name": f"Parcel {idx + 1}", "valid_from": f"{year}-01-01", "valid_to": f"{year}-12-31"}})
        add_features(db, layers[name], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Water bodies
    if not layers["Water Bodies (Demo)"].feature_count:
        feats = []
        for d in districts:
            for _ in range(3):
                cx, cy = rnd_point(d)
                t = rng.choices(["pond", "reservoir", "wetland"], [0.6, 0.15, 0.25])[0]
                r = {"pond": 0.015, "reservoir": 0.05, "wetland": 0.03}[t] * rng.uniform(0.7, 1.4)
                feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, r, 9), "properties": {"type": t, "area_ha": round((r * 100) ** 2 * 60, 1), "name": f"{t.title()} {len(feats) + 1}"}})
        add_features(db, layers["Water Bodies (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Forest density
    if not layers["Forest Cover Density (Demo)"].feature_count:
        feats = []
        for cx, cy, r, cls in parcels:
            if cls == "forest":
                dc = rng.choices(["very_dense", "moderately_dense", "open"], [0.3, 0.45, 0.25])[0]
                feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, r * 1.1), "properties": {"density_class": dc, "canopy_pct": {"very_dense": rng.uniform(70, 90), "moderately_dense": rng.uniform(40, 70), "open": rng.uniform(10, 40)}[dc]}})
        add_features(db, layers["Forest Cover Density (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Soil erosion
    if not layers["Soil Erosion Risk (Demo)"].feature_count:
        feats = []
        for d in districts:
            for _ in range(5):
                cx, cy = rnd_point(d)
                risk = rng.choices(["low", "moderate", "high", "severe"], [0.35, 0.35, 0.2, 0.1])[0]
                feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, rng.uniform(0.06, 0.14), 8), "properties": {"risk": risk, "soil_loss_t_ha": {"low": rng.uniform(1, 5), "moderate": rng.uniform(5, 10), "high": rng.uniform(10, 20), "severe": rng.uniform(20, 40)}[risk]}})
        add_features(db, layers["Soil Erosion Risk (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Groundwater wells (points)
    if not layers["Groundwater Observation Wells (Demo)"].feature_count:
        feats = []
        for d in districts:
            for _ in range(6):
                cx, cy = rnd_point(d)
                tr = rng.choices(["declining", "stable", "rising"], [0.45, 0.35, 0.2])[0]
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(cx, 5), round(cy, 5)]}, "properties": {"trend": tr, "depth_m_bgl": round(rng.uniform(4, 45), 1), "name": f"Well {len(feats) + 1}"}})
        add_features(db, layers["Groundwater Observation Wells (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Flood zones
    if not layers["Flood Hazard Zones (Demo)"].feature_count:
        feats = []
        for d in districts[:10]:
            cx, cy = rnd_point(d)
            for zone, rp, scale in (("A", 1, 0.05), ("B", 10, 0.09), ("C", 100, 0.13)):
                feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, scale, 9), "properties": {"zone": zone, "return_period_years": rp}})
        add_features(db, layers["Flood Hazard Zones (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Watershed projects (points)
    if not layers["Watershed Development Projects (Demo)"].feature_count:
        feats = []
        for d in districts:
            for _ in range(3):
                cx, cy = rnd_point(d)
                st = rng.choices(["completed", "ongoing", "planned"], [0.5, 0.3, 0.2])[0]
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(cx, 5), round(cy, 5)]}, "properties": {"status": st, "treated_area_ha": round(rng.uniform(800, 6000)), "name": f"Watershed project {len(feats) + 1}"}})
        add_features(db, layers["Watershed Development Projects (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    # Wasteland parcels
    if not layers["Wasteland Parcels (Demo)"].feature_count:
        feats = []
        for cx, cy, r, cls in parcels:
            if cls == "wasteland":
                cat = rng.choices(["scrub", "gullied", "salt_affected", "waterlogged"], [0.5, 0.2, 0.2, 0.1])[0]
                feats.append({"type": "Feature", "geometry": _random_blob(rng, cx, cy, r), "properties": {"category": cat, "reclamation_priority": rng.randint(1, 5)}})
        add_features(db, layers["Wasteland Parcels (Demo)"], {"type": "FeatureCollection", "features": feats}, is_demo=True)
    db.commit()
    return layers


def seed_datasets(db: Session, rng: random.Random, units: Dict[str, List[AdminUnit]], users: Dict[str, User]) -> List[Dataset]:
    owner = users[Roles.DATA_ANALYST]
    perms = {"dataset.approve"}
    src = db.scalar(select(DataSource).where(DataSource.name == "Demo Statistical Compendium"))
    if not src:
        src = DataSource(name="Demo Statistical Compendium", source_type="synthetic", organization="Bhoomitra demo", license="synthetic", description="Synthetic statistical series generated for platform demonstration", is_official=False, is_demo=True)
        db.add(src)
        db.flush()
    districts = units["districts"]
    specs = [
        ("District Cropping Intensity 2015-2023 (Demo)", DatasetCategory.AGRICULTURE, "cropping_intensity", "Cropping intensity", "%", 118, 2.4, 6),
        ("Post-monsoon Groundwater Depth 2015-2023 (Demo)", DatasetCategory.WATER, "gw_depth_m", "Groundwater depth below ground level", "m", 12.0, 0.55, 2.5),
        ("Land Record Digitisation Coverage 2015-2023 (Demo)", DatasetCategory.LAND_GOVERNANCE, "digitisation_pct", "Villages with digitised records", "%", 55, 5.0, 8),
        ("Pending Land Disputes per 10,000 Parcels 2015-2023 (Demo)", DatasetCategory.DISPUTES, "disputes_per_10k", "Pending disputes per 10,000 parcels", "count", 38, -1.8, 5),
        ("Wasteland Area 2015-2023 (Demo)", DatasetCategory.LAND_USE, "wasteland_km2", "Wasteland area", "km²", 1600, -22, 90),
        ("Rural Population 2015-2023 (Demo)", DatasetCategory.POPULATION, "population_k", "Rural population", "thousand", 900, 9.5, 120),
    ]
    out = []
    for name, cat, code, label, unit, base, slope, spread in specs:
        existing = db.scalar(select(Dataset).where(Dataset.name == name))
        if existing:
            out.append(existing)
            continue
        payload = DatasetCreate(name=name, description=f"{label} by demo district and year. Synthetic series generated with a deterministic seed; not official statistics.", category=cat, publisher="Bhoomitra demo", source_id=src.id, geography="All demo states", temporal_start=date(2015, 1, 1), temporal_end=date(2023, 12, 31), spatial_resolution="district", temporal_resolution="annual", license="synthetic", update_frequency="annual", quality_score=0.6, quality_notes="Synthetic; internally consistent but not validated", provenance="Generated by app/seed/demo.py", access_level="public", keywords=[code, "demo", "district"], variables=[DatasetVariableIn(code=code, name=label, unit=unit)])
        ds = dataset_service.create_dataset(db, payload, owner)
        ds.is_demo = True
        db.commit()
        rows = ["variable,admin_code,district,year,value,unit"]
        for d in districts:
            offset = rng.uniform(-spread, spread)
            for yr in range(2015, 2024):
                val = base + offset + slope * (yr - 2015) + rng.gauss(0, spread * 0.12)
                if code in ("cropping_intensity", "digitisation_pct"):
                    val = min(val, 100 if code == "digitisation_pct" else 220)
                rows.append(f"{code},{d.code},{d.name},{yr},{val:.2f},{unit}")
        data = "\n".join(rows).encode()
        dataset_service.upload_version(db, ds, data=data, filename=f"{code}.csv", declared_mime="text/csv", user=owner, perms=perms, change_note="Synthetic series", version_label="v1")
        db.refresh(ds)
        dataset_service.submit(db, ds, owner, perms)
        dataset_service.approve(db, ds, users[Roles.GOVERNMENT_OFFICIAL], "approve", "Demo data approved for demonstration")
        dataset_service.publish(db, ds, users[Roles.GOVERNMENT_OFFICIAL], "public")
        out.append(ds)
    db.commit()
    return out


def seed_documents(db: Session, users: Dict[str, User], orgs: Dict[str, Organization]) -> List[Document]:
    author = users[Roles.RESEARCHER]
    reviewer = users[Roles.GOVERNMENT_OFFICIAL]
    perms = {"document.review", "document.publish", "document.update", "document.create"}
    out = []
    for spec in DEMO_DOCUMENTS:
        existing = db.scalar(select(Document).where(Document.title == spec["title"]))
        if existing:
            out.append(existing)
            continue
        payload = DocumentCreate(title=spec["title"], description=spec["description"], abstract=None, authors=spec.get("authors", []), organization_id=orgs["nird-demo"].id, publisher="Bhoomitra demo", publication_date=date.fromisoformat(spec["publication_date"]), document_type=DocumentType(spec["document_type"]), topic=spec.get("topic"), policy_area=spec.get("policy_area"), research_area=spec.get("research_area"), geography=spec.get("geography"), keywords=spec.get("keywords", []), language="en", source="Demo / Synthetic Data", license="synthetic", visibility=Visibility.PUBLIC)
        doc = document_service.create_document(db, payload, author)
        doc.is_demo = True
        db.commit()
        body = (_HEADER + spec["title"] + "\n\n" + spec["text"]).encode("utf-8")
        version, job = document_service.upload_version(db, doc, data=body, filename=f"{doc.slug}.txt", declared_mime="text/plain", user=author, perms=perms, change_note="Synthetic demo text", version_label="v1")
        pipeline.process_version(db, version.id)
        db.refresh(doc)
        document_service.submit_for_review(db, doc, author, perms)
        document_service.review(db, doc, "approve", "Approved for demo", reviewer)
        document_service.publish(db, doc, reviewer, Visibility.PUBLIC)
        out.append(doc)
    # relations between related demo docs
    if len(out) >= 5:
        pairs = [(0, 4, "related"), (0, 10, "related"), (1, 5, "related"), (3, 11, "alternative"), (2, 9, "method")]
        for a, b, rel in pairs:
            try:
                document_service.add_relation(db, out[a], out[b].id, rel, author, perms)
            except Exception:
                db.rollback()
    db.commit()
    return out


def seed_policies(db: Session, rng: random.Random, users: Dict[str, User], units: Dict[str, List[AdminUnit]], docs: List[Document]) -> List[Policy]:
    pm = users[Roles.POLICY_MAKER]
    specs = [
        ("Model Land Record Modernisation Policy (Demo)", "land records", "national", "Demo Ministry", date(2016, 4, 1), PolicyStatus.ACTIVE, 0, [("digitisation_pct", "Villages with digitised records", "%", 55, 5)]),
        ("Watershed Development Guidelines 2.0 (Demo)", "watershed", "national", "Demo Ministry", date(2018, 7, 1), PolicyStatus.ACTIVE, 1, [("treated_area_kha", "Area treated", "thousand ha", 120, 34)]),
        ("Wasteland Reclamation Mission (Demo)", "wasteland", "national", "Demo Ministry", date(2020, 1, 15), PolicyStatus.ACTIVE, 2, [("reclaimed_km2", "Wasteland reclaimed", "km²", 40, 55)]),
        ("Model Agricultural Land Leasing Framework (Demo)", "tenure", "state", "Demo State 2", date(2017, 10, 1), PolicyStatus.ACTIVE, 9, [("recorded_lease_pct", "Leased area recorded", "%", 4, 6)]),
        ("Peri-urban Land Use Zoning Rules (Demo)", "urban", "state", "Demo State 3", date(2021, 9, 1), PolicyStatus.UNDER_REVIEW, 6, [("unauthorised_conversion_ha", "Unauthorised conversion detected", "ha", 1400, -180)]),
        ("Flood Hazard Zoning Regulation (Demo)", "disaster", "state", "Demo State 6", date(2023, 5, 1), PolicyStatus.DRAFT, 8, []),
        ("Property Card Issuance Scheme (Demo)", "land records", "national", "Demo Ministry", date(2020, 4, 24), PolicyStatus.ACTIVE, 4, [("cards_issued_k", "Property cards issued", "thousand", 20, 45)]),
        ("Land Acquisition Compensation Guidelines 2013-style (Demo)", "land acquisition", "national", "Demo Ministry", date(2014, 1, 1), PolicyStatus.SUPERSEDED, 3, []),
    ]
    out = []
    for title, area, level, ministry, eff, status, doc_idx, indicators in specs:
        p = db.scalar(select(Policy).where(Policy.title == title))
        if not p:
            p = Policy(title=title, slug=unique_slug(db, Policy, title), summary=f"Synthetic policy entry for demonstration: {title}. See linked document for narrative context.", policy_area=area, level=level, ministry=ministry, effective_date=eff, status=status, document_id=docs[doc_idx].id if doc_idx < len(docs) else None, geography=ministry if level == "state" else "All demo states", created_by=pm.id, is_demo=True)
            db.add(p)
            db.flush()
            for code, name, unit, base, slope in indicators:
                for yr in range(2016, 2024):
                    db.add(PolicyIndicator(policy_id=p.id, code=code, name=name, unit=unit, value=round(base + slope * (yr - 2016) + rng.gauss(0, abs(slope) * 0.2 + 0.5), 2), period_start=date(yr, 1, 1), period_end=date(yr, 12, 31), value_kind="OBSERVED", is_demo=True))
        out.append(p)
    db.commit()
    return out


def seed_research(db: Session, users: Dict[str, User], orgs: Dict[str, Organization], docs: List[Document], datasets: List[Dataset]) -> List[ResearchProject]:
    specs = [
        ("Drone Survey Cost-Benefit in Resurvey Districts (Demo)", "land records", Roles.RESEARCHER, "nird-demo", ResearchStatus.ACTIVE, date(2023, 1, 1), None, 0),
        ("Groundwater Response to Watershed Treatment (Demo)", "hydrology", Roles.ACADEMIC, "demo-state-university", ResearchStatus.COMPLETED, date(2020, 6, 1), date(2022, 12, 31), 1),
        ("Salinity Mapping in Canal Commands (Demo)", "remote sensing", Roles.RESEARCH_ORG, "nird-demo", ResearchStatus.ACTIVE, date(2022, 4, 1), None, 5),
        ("Tenancy Formalisation and Credit Access (Demo)", "tenure", Roles.RESEARCHER, "nird-demo", ResearchStatus.PUBLISHED, date(2018, 1, 1), date(2020, 3, 31), 9),
    ]
    out = []
    for title, area, role, org, status, start, end, doc_idx in specs:
        p = db.scalar(select(ResearchProject).where(ResearchProject.title == title))
        if not p:
            p = ResearchProject(title=title, summary=f"Synthetic research project: {title}.", research_area=area, geography="Demo states", lead_user_id=users[role].id, organization_id=orgs[org].id, status=status, start_date=start, end_date=end, funding_source="Demo grant", keywords=[area, "demo"], is_demo=True)
            db.add(p)
            db.flush()
            db.add(ResearchOutput(project_id=p.id, output_type="paper", title=docs[doc_idx].title, document_id=docs[doc_idx].id))
            if datasets:
                db.add(ResearchOutput(project_id=p.id, output_type="dataset", title=datasets[min(doc_idx, len(datasets) - 1)].name, dataset_id=datasets[min(doc_idx, len(datasets) - 1)].id))
        out.append(p)
    db.commit()
    return out


def seed_scenarios(db: Session, users: Dict[str, User], units: Dict[str, List[AdminUnit]], layers: Dict[str, GISLayer], datasets: List[Dataset]) -> None:
    pm = users[Roles.POLICY_MAKER]
    if db.scalar(select(func.count()).select_from(__import__("app.models.intelligence", fromlist=["Scenario"]).Scenario)) > 0:
        return
    lulc = layers["Land Use Land Cover 2023 (Demo)"]
    d = units["districts"][0]
    pop_ds = next((x for x in datasets if "Population" in x.name), None)
    common = {"population_k": 920, "rainfall_mm": 950, "base_year": 2024}
    specs = [
        ("Baseline — business as usual (Demo)", [], "Reference projection with no intervention."),
        ("Afforest 120 km² of wasteland (Demo)", [{"type": "reallocate", "from_class": "wasteland", "to_class": "forest", "area_km2": 120, "start_year_offset": 1, "ramp_years": 5}], "Plantation on scrub and gullied wasteland."),
        ("Peri-urban expansion on cropland (Demo)", [{"type": "reallocate", "from_class": "cropland", "to_class": "built_up", "area_km2": 90, "start_year_offset": 1, "ramp_years": 6}], "Unplanned conversion of irrigated cropland."),
        ("Irrigation + yield programme (Demo)", [{"type": "irrigation_expansion", "area_km2": 150, "start_year_offset": 1, "ramp_years": 4}, {"type": "yield_improvement", "pct": 12, "start_year_offset": 2, "ramp_years": 4}], "Micro-irrigation expansion with extension support."),
    ]
    for name, interventions, desc in specs:
        sc = sim.create_scenario(db, name=name, description=desc, baseline=common, interventions=interventions, constraints=None, horizon_years=12, admin_unit_id=d.id, baseline_layer_id=lulc.id, baseline_dataset_version_id=pop_ds.current_version_id if pop_ds else None, workspace_id=None, parent_scenario_id=None, user_id=pm.id, is_demo=True)
        sim.run_scenario(db, sc, iterations=400, seed=7, user_id=pm.id)
    db.commit()


def seed_innovation(db: Session, rng: random.Random, users: Dict[str, User], orgs: Dict[str, Organization], units: Dict[str, List[AdminUnit]]) -> None:
    if db.scalar(select(func.count(Challenge.id)).where(Challenge.is_demo.is_(True))):
        return
    pm = users[Roles.PROJECT_MANAGER]
    ev = users[Roles.INNOVATION_EVALUATOR]
    expert = users[Roles.EXPERT]
    researcher = users[Roles.RESEARCHER]
    from app.api.v1.innovation import DEFAULT_CRITERIA, _weighted_score

    now = _now()
    specs = [
        ("Low-cost drone survey workflow for village boundaries (Demo)", "innovation_challenge", "land records", ChallengeStatus.OPEN, now - timedelta(days=20), now + timedelta(days=60), "Seeking end-to-end workflows that cut per-village survey cost by half while meeting accuracy norms."),
        ("AI-assisted extraction from legacy cadastral maps (Demo)", "research_call", "land records", ChallengeStatus.EVALUATION, now - timedelta(days=120), now - timedelta(days=10), "Methods to vectorise deteriorated cloth and paper maps with topological validation."),
        ("Community groundwater monitoring pilots (Demo)", "pilot_programme", "water", ChallengeStatus.PILOT, now - timedelta(days=400), now - timedelta(days=300), "Village-level monitoring with low-cost sensors feeding the platform."),
        ("Land dispute early-warning analytics (Demo)", "hackathon", "disputes", ChallengeStatus.COMPLETED, now - timedelta(days=700), now - timedelta(days=640), "Predict dispute hotspots from mutation delays and record inconsistencies."),
    ]
    for title, ctype, theme, status, opens, closes, summary in specs:
        c = Challenge(title=title, slug=unique_slug(db, Challenge, title), challenge_type=ctype, summary=summary, description=summary + " (Synthetic challenge for demonstration.)", theme=theme, eligibility="Start-ups, research institutions, individuals", evaluation_criteria=DEFAULT_CRITERIA, prize_or_grant="Pilot funding (demo)", opens_at=opens, closes_at=closes, status=status, organization_id=orgs["dolr-demo"].id, created_by=pm.id, is_demo=True)
        db.add(c)
        db.flush()
        if status == ChallengeStatus.OPEN:
            db.add(Submission(challenge_id=c.id, applicant_id=expert.id, organization_id=orgs["geoinnovate-demo"].id, title="Photogrammetry-first survey kit (Demo)", abstract="Consumer drones with RTK modules and automated boundary extraction.", proposal="Synthetic proposal text.", team_name="GeoInnovate", status="submitted", submitted_at=now - timedelta(days=3)))
        elif status in (ChallengeStatus.EVALUATION, ChallengeStatus.PILOT, ChallengeStatus.COMPLETED):
            for i, (applicant, org, t) in enumerate(((expert, "geoinnovate-demo", "Deep learning vectoriser (Demo)"), (researcher, "nird-demo", "Semi-automatic tracing with topology checks (Demo)"))):
                s = Submission(challenge_id=c.id, applicant_id=applicant.id, organization_id=orgs[org].id, title=t, abstract="Synthetic abstract.", proposal="Synthetic proposal text.", team_name=f"Team {i + 1}", status="under_evaluation" if status == ChallengeStatus.EVALUATION else ("shortlisted" if i == 0 else "not_selected"), submitted_at=closes - timedelta(days=2))
                db.add(s)
                db.flush()
                scores = {cr["code"]: rng.randint(5, 9) for cr in DEFAULT_CRITERIA}
                w = _weighted_score(DEFAULT_CRITERIA, scores)
                db.add(Evaluation(submission_id=s.id, evaluator_id=ev.id, scores=scores, total_score=w, comments="Synthetic evaluation.", recommendation="shortlist" if i == 0 else "consider"))
                s.total_score = w
                if status in (ChallengeStatus.PILOT, ChallengeStatus.COMPLETED) and i == 0:
                    s.status = "pilot"
                    db.add(Pilot(submission_id=s.id, challenge_id=c.id, title=f"Pilot: {t}", admin_unit_id=units["districts"][2].id, start_date=(closes + timedelta(days=30)).date(), end_date=(closes + timedelta(days=210)).date(), status="active" if status == ChallengeStatus.PILOT else "completed", outcome_summary=None if status == ChallengeStatus.PILOT else "Synthetic pilot completed with positive assessment.", manager_id=pm.id, budget=2500000, kpis=[{"name": "Villages covered", "target": 40}], is_demo=True))
    db.commit()


def seed_workspaces(db: Session, users: Dict[str, User], orgs: Dict[str, Organization], docs: List[Document], datasets: List[Dataset]) -> None:
    if db.scalar(select(func.count(Workspace.id)).where(Workspace.is_demo.is_(True))):
        return
    pm = users[Roles.PROJECT_MANAGER]
    specs = [
        ("Demo State 1 Resurvey Programme Review", "Assess drone resurvey outcomes and plan scale-up", WorkspaceStatus.ACTIVE, [Roles.GIS_ANALYST, Roles.RESEARCHER, Roles.GOVERNMENT_OFFICIAL]),
        ("Wasteland Reclamation Priority Study", "Combine wasteland atlas with watershed data to rank reclamation parcels", WorkspaceStatus.DRAFT, [Roles.DATA_ANALYST, Roles.ACADEMIC]),
    ]
    for name, objective, status, roles in specs:
        ws = Workspace(name=name, slug=unique_slug(db, Workspace, name), description=objective, objective=objective, status=status, organization_id=orgs["dolr-demo"].id, owner_id=pm.id, is_public=True, tags=["demo"], is_demo=True)
        db.add(ws)
        db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=pm.id, role="owner", invited_by=pm.id))
        for r in roles:
            db.add(WorkspaceMember(workspace_id=ws.id, user_id=users[r].id, role="editor", invited_by=pm.id))
        db.add(WorkspaceResource(workspace_id=ws.id, resource_type="document", resource_id=docs[0].id, title=docs[0].title, added_by=pm.id))
        if datasets:
            db.add(WorkspaceResource(workspace_id=ws.id, resource_type="dataset", resource_id=datasets[0].id, title=datasets[0].name, added_by=pm.id))
        db.add(Task(workspace_id=ws.id, title="Validate baseline datasets", status="in_progress", priority="high", assignee_id=users[roles[0]].id, due_date=(date.today() + timedelta(days=14)), created_by=pm.id))
        db.add(Task(workspace_id=ws.id, title="Draft policy brief", status="todo", priority="medium", assignee_id=users[roles[-1]].id, due_date=(date.today() + timedelta(days=30)), created_by=pm.id))
        db.add(Comment(target_type="workspace", target_id=ws.id, workspace_id=ws.id, author_id=pm.id, body="Kick-off: please review the linked demo documents and datasets."))
    db.commit()


def seed_demo(db: Session, force: bool = False) -> Dict[str, Any]:
    if already_seeded(db) and not force:
        return {"status": "skipped", "reason": "demo data already seeded"}
    rng = random.Random(20260905)
    orgs = seed_organizations(db)
    users = seed_users(db, orgs)
    units = seed_admin_units(db, rng)
    layers = seed_layers(db, rng, units, users[Roles.GIS_ANALYST])
    datasets = seed_datasets(db, rng, units, users)
    docs = seed_documents(db, users, orgs)
    policies = seed_policies(db, rng, users, units, docs)
    research = seed_research(db, users, orgs, docs, datasets)
    seed_scenarios(db, users, units, layers, datasets)
    seed_innovation(db, rng, users, orgs, units)
    seed_workspaces(db, users, orgs, docs, datasets)
    marker = db.scalar(select(SystemSetting).where(SystemSetting.key == SEED_MARKER))
    if not marker:
        db.add(SystemSetting(key=SEED_MARKER, value=_now().isoformat(), value_type="string", description="Demo / Synthetic Data seeded at"))
    else:
        marker.value = _now().isoformat()
    db.commit()
    summary = {"status": "seeded", "organizations": len(orgs), "users": len(users), "states": len(units["states"]), "districts": len(units["districts"]), "layers": len(layers), "datasets": len(datasets), "documents": len(docs), "policies": len(policies), "research_projects": len(research), "demo_password": DEMO_PASSWORD}
    logger.info("demo data seeded", extra={"extra_data": summary})
    return summary
