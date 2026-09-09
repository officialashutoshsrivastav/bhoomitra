from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DependencyUnavailable, NotFoundError, ValidationFailed
from app.models.gis import AdminLevel, AdminUnit
from app.models.platform import IntegrationConfig

CONNECTORS: Dict[str, Dict[str, Any]] = {
    "geoboundaries": {"display_name": "geoBoundaries administrative boundaries", "kind": "boundaries", "description": "Open administrative boundaries (ADM0–ADM2) under CC BY 4.0. Loaded on demand via scripts/load_boundaries.py or the /load endpoint (network required).", "docs": "https://www.geoboundaries.org", "settings": ["GEOBOUNDARIES_BASE_URL"]},
    "datagov_in": {"display_name": "data.gov.in Open Government Data", "kind": "open_data", "description": "OGD Platform India catalogue/resource API. Requires DATAGOV_API_KEY for live queries; demo mode returns catalogue stubs.", "docs": "https://data.gov.in", "settings": ["DATAGOV_API_KEY", "DATAGOV_BASE_URL"]},
    "stac_satellite": {"display_name": "Satellite imagery (STAC)", "kind": "remote_sensing", "description": "STAC catalogue search for Sentinel-2/Landsat scenes (e.g. Planetary Computer, Copernicus Data Space). Demo connector generates synthetic reflectance.", "docs": "https://stacspec.org", "settings": ["STAC_ENDPOINT"]},
    "opensearch": {"display_name": "OpenSearch keyword index", "kind": "search", "description": "Optional keyword/autocomplete engine. Falls back to PostgreSQL full-text search when unavailable.", "settings": ["OPENSEARCH_URL", "OPENSEARCH_INDEX_PREFIX"]},
    "object_storage": {"display_name": "Object storage (S3/MinIO)", "kind": "storage", "description": "Document, dataset and report file storage. Local filesystem backend is used in development.", "settings": ["STORAGE_BACKEND", "S3_ENDPOINT_URL", "S3_BUCKET"]},
    "openai": {"display_name": "LLM & embedding provider (OpenAI-compatible)", "kind": "ai", "description": "Generative answers and semantic embeddings. Without a key the platform uses deterministic hashing embeddings and extractive, citation-only answers.", "settings": ["AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_CHAT_MODEL", "EMBEDDING_PROVIDER"]},
    "email": {"display_name": "Email delivery (SMTP)", "kind": "notifications", "description": "Transactional email for activation, password reset and notifications. Console provider logs emails in development.", "settings": ["EMAIL_BACKEND", "SMTP_HOST", "SMTP_PORT"]},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_rows(db: Session) -> None:
    for key, meta in CONNECTORS.items():
        if not db.scalar(select(IntegrationConfig.id).where(IntegrationConfig.connector == key)):
            db.add(IntegrationConfig(connector=key, display_name=meta["display_name"], kind=meta["kind"], enabled=True, mode="demo", config={}))
    db.commit()


def _live_mode(key: str) -> bool:
    return {
        "geoboundaries": True,  # network fetch only, no key required
        "datagov_in": bool(settings.datagov_api_key),
        "stac_satellite": bool(settings.stac_endpoint),
        "opensearch": bool(settings.opensearch_url),
        "object_storage": settings.storage_backend == "s3",
        "openai": settings.ai_provider == "openai" and bool(settings.openai_api_key),
        "email": settings.email_backend == "smtp",
    }.get(key, False)


def check(db: Session, key: str) -> Dict[str, Any]:
    if key not in CONNECTORS:
        raise NotFoundError("Unknown connector")
    row = db.scalar(select(IntegrationConfig).where(IntegrationConfig.connector == key))
    status, message = "ok", ""
    try:
        if key == "opensearch":
            from app.search.opensearch_client import opensearch_status

            st = opensearch_status()
            status = "ok" if st.get("ok") and st.get("configured") else ("fallback" if not settings.opensearch_url else "error")
            message = st.get("note") or st.get("error") or f"cluster {st.get('cluster_status')}"
        elif key == "object_storage":
            from app.storage.service import get_storage

            ok, detail = get_storage().health()
            status = "ok" if ok else "error"
            message = f"{settings.storage_backend}: {detail}"
        elif key == "openai":
            if _live_mode(key):
                import httpx

                r = httpx.get(f"{settings.openai_base_url}/models", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, timeout=10)
                status = "ok" if r.status_code == 200 else "error"
                message = f"HTTP {r.status_code}"
            else:
                status, message = "fallback", "No API key — extractive answers + hashing embeddings"
        elif key == "email":
            status, message = ("ok", f"SMTP {settings.smtp_host}:{settings.smtp_port}") if settings.email_backend == "smtp" else ("fallback", "console email provider (logs only)")
        elif key == "stac_satellite":
            if settings.stac_endpoint:
                import httpx

                r = httpx.get(settings.stac_endpoint, timeout=10)
                status = "ok" if r.status_code < 400 else "error"
                message = f"HTTP {r.status_code}"
            else:
                status, message = "demo", "Demo connector (synthetic scenes)"
        elif key == "datagov_in":
            status, message = ("configured", "API key present; live queries enabled") if settings.datagov_api_key else ("demo", "No API key — catalogue stubs only")
        elif key == "geoboundaries":
            n = db.scalar(select(func.count(AdminUnit.id)).where(AdminUnit.source == "geoBoundaries")) or 0
            status, message = ("ok", f"{n} boundary units loaded") if n else ("not_loaded", "No geoBoundaries units loaded; demo boundaries in use")
    except Exception as exc:  # pragma: no cover
        status, message = "error", str(exc)[:300]
    if row:
        row.last_checked_at = _now()
        row.last_status = status
        row.last_message = message
        row.mode = "live" if _live_mode(key) else "demo"
        db.commit()
    return {"connector": key, "status": status, "message": message, "mode": "live" if _live_mode(key) else "demo", "checked_at": _now().isoformat()}


def list_all(db: Session) -> List[Dict[str, Any]]:
    ensure_rows(db)
    rows = {r.connector: r for r in db.scalars(select(IntegrationConfig)).all()}
    out = []
    for key, meta in CONNECTORS.items():
        r = rows.get(key)
        out.append({"connector": key, **meta, "enabled": r.enabled if r else True, "mode": "live" if _live_mode(key) else "demo", "last_status": r.last_status if r else None, "last_message": r.last_message if r else None, "last_checked_at": r.last_checked_at.isoformat() if r and r.last_checked_at else None, "config": {k: v for k, v in (r.config or {}).items() if "secret" not in k and "key" not in k} if r else {}})
    return out


def set_enabled(db: Session, key: str, enabled: bool, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ensure_rows(db)
    row = db.scalar(select(IntegrationConfig).where(IntegrationConfig.connector == key))
    if not row:
        raise NotFoundError("Unknown connector")
    row.enabled = enabled
    if config is not None:
        row.config = {**(row.config or {}), **{k: v for k, v in config.items() if not isinstance(v, (dict, list))}}
    db.commit()
    return {"connector": key, "enabled": row.enabled, "config": row.config}


# ---------------------------------------------------------------------------
# geoBoundaries loader (live network)
# ---------------------------------------------------------------------------
def load_geoboundaries(db: Session, iso3: str = "IND", adm: str = "ADM1", replace: bool = False, timeout: int = 120) -> Dict[str, Any]:
    """Fetches geoBoundaries GeoJSON (CC BY 4.0) and upserts admin units. ADM1 = states/UTs, ADM2 = districts."""
    import httpx

    level = {"ADM0": AdminLevel.COUNTRY, "ADM1": AdminLevel.STATE, "ADM2": AdminLevel.DISTRICT}.get(adm.upper())
    if not level:
        raise ValidationFailed("adm must be ADM0, ADM1 or ADM2")
    meta_url = f"{settings.geoboundaries_base_url.rstrip('/')}/{iso3}/{adm.upper()}/"
    try:
        meta = httpx.get(meta_url, timeout=timeout, follow_redirects=True)
        meta.raise_for_status()
        gj_url = meta.json().get("gjDownloadURL") or meta.json().get("simplifiedGeometryGeoJSON")
        gj = httpx.get(gj_url, timeout=timeout, follow_redirects=True)
        gj.raise_for_status()
        fc = gj.json()
    except Exception as exc:
        raise DependencyUnavailable(f"geoBoundaries fetch failed: {exc}")
    parents = {u.name.lower(): u for u in db.scalars(select(AdminUnit).where(AdminUnit.level == AdminLevel.STATE)).all()} if level == AdminLevel.DISTRICT else {}
    country = db.scalar(select(AdminUnit).where(AdminUnit.level == AdminLevel.COUNTRY, AdminUnit.code == iso3))
    if level != AdminLevel.COUNTRY and not country:
        country = AdminUnit(name="India", code=iso3, level=AdminLevel.COUNTRY, source="geoBoundaries", source_license="CC BY 4.0", is_demo=False)
        db.add(country)
        db.flush()
    n = 0
    for ft in fc.get("features", []):
        props = ft.get("properties", {})
        name = props.get("shapeName") or props.get("name")
        code = props.get("shapeID") or props.get("shapeISO") or name
        if not name or not ft.get("geometry"):
            continue
        existing = db.scalar(select(AdminUnit).where(AdminUnit.code == code, AdminUnit.level == level))
        geom = func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(ft["geometry"])), 4326))
        parent_id = None
        if level == AdminLevel.DISTRICT:
            pname = (props.get("shapeGroup") or "").lower()
            parent_id = parents.get(pname).id if pname in parents else None
        elif level == AdminLevel.STATE and country:
            parent_id = country.id
        if existing and not replace:
            continue
        if existing:
            existing.geom = geom
            existing.name = name
            existing.parent_id = parent_id or existing.parent_id
            unit = existing
        else:
            unit = AdminUnit(name=name, code=str(code)[:50], level=level, parent_id=parent_id, geom=geom, source="geoBoundaries", source_license="CC BY 4.0", is_demo=False)
            db.add(unit)
        n += 1
        if n % 100 == 0:
            db.flush()
    db.flush()
    from app.gis.service import refresh_unit_metrics

    for u in db.scalars(select(AdminUnit).where(AdminUnit.level == level, AdminUnit.source == "geoBoundaries")).all():
        refresh_unit_metrics(db, u)
    db.commit()
    return {"iso3": iso3, "adm": adm.upper(), "loaded": n, "license": "CC BY 4.0", "attribution": "geoBoundaries (Runfola et al.)"}
