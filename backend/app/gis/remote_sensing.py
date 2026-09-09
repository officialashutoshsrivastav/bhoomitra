from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.gis import AdminUnit, RSProduct, RSScene
from app.models.intelligence import AnalysisModel, ModelVersion, NodeType
from app.services import evidence_service


@dataclass
class SceneBands:
    red: np.ndarray
    nir: np.ndarray
    green: Optional[np.ndarray] = None
    swir: Optional[np.ndarray] = None
    resolution_m: float = 10.0


# ---------------------------------------------------------------------------
# Connector interface
# ---------------------------------------------------------------------------
class SatelliteConnector(ABC):
    name = "abstract"
    mode = "demo"

    @abstractmethod
    def search(self, bbox: Tuple[float, float, float, float], start: date, end: date, max_cloud: float = 30.0, limit: int = 10) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def load_bands(self, scene: RSScene, bbox: Optional[Tuple[float, float, float, float]] = None) -> SceneBands: ...


class STACConnector(SatelliteConnector):
    """Connector for STAC catalogues (e.g. Microsoft Planetary Computer, Copernicus
    Data Space, Element84 Earth Search). Searches scenes and records asset URIs;
    band loading requires network access + a raster reader (rasterio) and is
    therefore surfaced as an explicit dependency."""

    name = "stac"
    mode = "live"

    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    def search(self, bbox, start, end, max_cloud=30.0, limit=10):
        import httpx

        body = {"bbox": list(bbox), "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z", "collections": ["sentinel-2-l2a"], "limit": limit, "query": {"eo:cloud_cover": {"lt": max_cloud}}}
        resp = httpx.post(f"{self.endpoint}/search", json=body, timeout=30)
        resp.raise_for_status()
        out = []
        for item in resp.json().get("features", []):
            props = item.get("properties", {})
            out.append({"scene_id": item["id"], "source": "sentinel-2", "acquisition_date": props.get("datetime", "")[:10], "cloud_cover": props.get("eo:cloud_cover"), "resolution_m": 10.0, "bbox": item.get("bbox"), "assets": {k: v.get("href") for k, v in item.get("assets", {}).items() if k in ("B02", "B03", "B04", "B08", "B11", "red", "green", "blue", "nir", "swir16")}, "provenance": {"catalog": self.endpoint, "collection": item.get("collection"), "license": props.get("license")}})
        return out

    def load_bands(self, scene, bbox=None):
        raise ValidationFailed("Loading raster bands from a live STAC catalogue requires network access and rasterio; install rasterio and configure STAC_ENDPOINT, or use the demo connector.")


class DemoSatelliteConnector(SatelliteConnector):
    """Deterministic synthetic scenes for development. Every scene/product is
    flagged is_demo=True and labelled 'Demo / Synthetic Data'."""

    name = "demo"
    mode = "demo"

    def search(self, bbox, start, end, max_cloud=30.0, limit=10):
        out = []
        cur = start
        i = 0
        while cur <= end and len(out) < limit:
            out.append({"scene_id": f"DEMO-S2-{cur.isoformat()}-{i}", "source": "demo-sentinel-2", "acquisition_date": cur.isoformat(), "cloud_cover": float(5 + (i * 7) % 25), "resolution_m": 10.0, "bbox": list(bbox), "assets": {}, "provenance": {"catalog": "demo", "note": "Demo / Synthetic Data"}})
            cur = date.fromordinal(cur.toordinal() + 30)
            i += 1
        return out

    def load_bands(self, scene, bbox=None):
        seed = int.from_bytes(scene.scene_id.encode("utf-8")[-4:], "little") % (2**31)
        rng = np.random.default_rng(seed)
        h = w = 96
        yy, xx = np.mgrid[0:h, 0:w]
        # spatially coherent fields: vegetation gradient, a water body, an urban patch
        veg = 0.45 + 0.35 * np.sin(xx / 18.0) * np.cos(yy / 22.0)
        water = ((xx - 70) ** 2 + (yy - 25) ** 2) < 140
        urban = (xx < 28) & (yy > 60)
        day_of_year = scene.acquisition_date.timetuple().tm_yday if scene.acquisition_date else 180
        season = 0.85 + 0.15 * np.cos((day_of_year - 240) / 365 * 2 * np.pi)
        nir = np.clip((0.15 + 0.7 * veg) * season + rng.normal(0, 0.03, (h, w)), 0.02, 0.95)
        red = np.clip(0.05 + 0.3 * (1 - veg * season) + rng.normal(0, 0.02, (h, w)), 0.02, 0.9)
        green = np.clip(0.25 + 0.1 * veg + rng.normal(0, 0.02, (h, w)), 0.02, 0.9)
        swir = np.clip(0.3 + 0.2 * (1 - veg) + rng.normal(0, 0.02, (h, w)), 0.02, 0.9)
        nir[water], red[water], green[water], swir[water] = 0.05, 0.06, 0.12, 0.03
        nir[urban], red[urban], green[urban], swir[urban] = 0.30, 0.34, 0.30, 0.45
        return SceneBands(red=red, nir=nir, green=green, swir=swir, resolution_m=10.0)


def get_connector() -> SatelliteConnector:
    if settings.stac_endpoint:
        return STACConnector(settings.stac_endpoint)
    return DemoSatelliteConnector()


# ---------------------------------------------------------------------------
# Index mathematics (real, provider-independent)
# ---------------------------------------------------------------------------
def _safe_ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(denom) < 1e-6, 0.0, (a - b) / denom)
    return np.clip(out, -1, 1)


def ndvi(b: SceneBands) -> np.ndarray:
    return _safe_ratio(b.nir, b.red)


def ndwi(b: SceneBands) -> np.ndarray:
    if b.green is None:
        raise ValidationFailed("NDWI requires a green band")
    return _safe_ratio(b.green, b.nir)


def ndbi(b: SceneBands) -> np.ndarray:
    if b.swir is None:
        raise ValidationFailed("NDBI requires a SWIR band")
    return _safe_ratio(b.swir, b.nir)


def _stats(arr: np.ndarray) -> Dict[str, float]:
    return {"mean": round(float(np.mean(arr)), 4), "std": round(float(np.std(arr)), 4), "min": round(float(np.min(arr)), 4), "max": round(float(np.max(arr)), 4), "p10": round(float(np.percentile(arr, 10)), 4), "p90": round(float(np.percentile(arr, 90)), 4)}


LULC_CLASSES = ["water", "built_up", "barren", "sparse_vegetation", "cropland", "dense_vegetation"]


def classify_lulc(b: SceneBands) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Rule-based land-cover classification from spectral indices (transparent,
    documented thresholds). It is a MODELLED estimate, not ground truth."""
    v, w = ndvi(b), ndwi(b) if b.green is not None else np.zeros_like(b.nir)
    bi = ndbi(b) if b.swir is not None else np.zeros_like(b.nir)
    cls = np.full(v.shape, 2, dtype=np.int8)  # barren
    cls[(v > 0.2) & (v <= 0.4)] = 3
    cls[(v > 0.4) & (v <= 0.6)] = 4
    cls[v > 0.6] = 5
    cls[(bi > 0.05) & (v < 0.3)] = 1
    cls[w > 0.2] = 0
    pixel_km2 = (b.resolution_m ** 2) / 1e6
    counts = {LULC_CLASSES[i]: int((cls == i).sum()) for i in range(len(LULC_CLASSES))}
    total = cls.size
    shares = {k: round(100 * c / total, 2) for k, c in counts.items()}
    areas = {k: round(c * pixel_km2, 4) for k, c in counts.items()}
    return cls, {"classes": LULC_CLASSES, "pixel_counts": counts, "share_pct": shares, "area_km2": areas, "thresholds": {"water": "NDWI > 0.2", "built_up": "NDBI > 0.05 and NDVI < 0.3", "dense_vegetation": "NDVI > 0.6", "cropland": "0.4 < NDVI <= 0.6", "sparse_vegetation": "0.2 < NDVI <= 0.4", "barren": "otherwise"}}


def change_detection(before: SceneBands, after: SceneBands) -> Dict[str, Any]:
    if before.nir.shape != after.nir.shape:
        raise ValidationFailed("Scenes must have identical raster grids for change detection")
    dv = ndvi(after) - ndvi(before)
    pixel_km2 = (after.resolution_m ** 2) / 1e6
    loss = dv < -0.15
    gain = dv > 0.15
    cb, _ = classify_lulc(before)
    ca, _ = classify_lulc(after)
    transitions: Dict[str, int] = {}
    for i in range(len(LULC_CLASSES)):
        for j in range(len(LULC_CLASSES)):
            if i != j:
                n = int(((cb == i) & (ca == j)).sum())
                if n:
                    transitions[f"{LULC_CLASSES[i]}->{LULC_CLASSES[j]}"] = n
    water_before, water_after = int((cb == 0).sum()), int((ca == 0).sum())
    urban_before, urban_after = int((cb == 1).sum()), int((ca == 1).sum())
    return {
        "ndvi_delta": _stats(dv),
        "vegetation_loss_km2": round(float(loss.sum()) * pixel_km2, 4),
        "vegetation_gain_km2": round(float(gain.sum()) * pixel_km2, 4),
        "water_change_km2": round((water_after - water_before) * pixel_km2, 4),
        "urban_expansion_km2": round((urban_after - urban_before) * pixel_km2, 4),
        "top_transitions": dict(sorted(transitions.items(), key=lambda kv: -kv[1])[:8]),
        "method": "NDVI difference (±0.15 threshold) + rule-based LULC transition matrix",
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _model_version(db: Session) -> ModelVersion:
    model = db.scalar(select(AnalysisModel).where(AnalysisModel.slug == "rs-index-lulc"))
    if not model:
        model = AnalysisModel(name="Spectral index & rule-based LULC classifier", slug="rs-index-lulc", model_type="remote_sensing", objective="Derive NDVI/NDWI/NDBI and a transparent rule-based land-cover map from multispectral reflectance")
        db.add(model)
        db.flush()
        mv = ModelVersion(model_id=model.id, version="1.0.0", algorithm="normalised-difference indices + threshold rules", features=["red", "nir", "green", "swir"], parameters={"ndvi_dense": 0.6, "ndvi_crop": 0.4, "ndvi_sparse": 0.2, "ndwi_water": 0.2, "ndbi_builtup": 0.05}, limitations="Thresholds are generic; not calibrated per region/season; no atmospheric correction handling; cloud/shadow masking not applied.", is_default=True)
        db.add(mv)
        db.flush()
        return mv
    return db.scalar(select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.is_default.is_(True))) or model.versions[-1]


def register_scenes(db: Session, bbox: Tuple[float, float, float, float], start: date, end: date, max_cloud: float, limit: int) -> List[RSScene]:
    conn = get_connector()
    found = conn.search(bbox, start, end, max_cloud, limit)
    scenes = []
    for f in found:
        existing = db.scalar(select(RSScene).where(RSScene.source == f["source"], RSScene.scene_id == f["scene_id"]))
        if existing:
            scenes.append(existing)
            continue
        bb = f.get("bbox") or list(bbox)
        poly = json.dumps({"type": "Polygon", "coordinates": [[[bb[0], bb[1]], [bb[2], bb[1]], [bb[2], bb[3]], [bb[0], bb[3]], [bb[0], bb[1]]]]})
        s = RSScene(source=f["source"], scene_id=f["scene_id"], acquisition_date=date.fromisoformat(f["acquisition_date"]) if f.get("acquisition_date") else None, resolution_m=f.get("resolution_m"), cloud_cover=f.get("cloud_cover"), bounds=func.ST_SetSRID(func.ST_GeomFromGeoJSON(poly), 4326), bands=f.get("assets") or {}, provenance=f.get("provenance"), processing_status="REGISTERED", is_demo=conn.mode == "demo")
        db.add(s)
        db.flush()
        scenes.append(s)
    db.commit()
    return scenes


def get_scene(db: Session, scene_id: uuid.UUID) -> RSScene:
    s = db.get(RSScene, scene_id)
    if not s:
        raise NotFoundError("Scene not found")
    return s


def derive_product(db: Session, scene: RSScene, product_type: str, admin_unit_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID]) -> RSProduct:
    conn = get_connector()
    scene.processing_status = "PROCESSING"
    db.commit()
    try:
        bands = conn.load_bands(scene)
        mv = _model_version(db)
        if product_type == "ndvi":
            stats = {"index": "NDVI", **_stats(ndvi(bands))}
            method = "(NIR - Red) / (NIR + Red)"
        elif product_type == "ndwi":
            stats = {"index": "NDWI", **_stats(ndwi(bands))}
            method = "(Green - NIR) / (Green + NIR)"
        elif product_type == "ndbi":
            stats = {"index": "NDBI", **_stats(ndbi(bands))}
            method = "(SWIR - NIR) / (SWIR + NIR)"
        elif product_type == "lulc":
            _, stats = classify_lulc(bands)
            method = "rule-based classification on NDVI/NDWI/NDBI"
        else:
            raise ValidationFailed("product_type must be ndvi|ndwi|ndbi|lulc")
        product = RSProduct(scene_id=scene.id, product_type=product_type, admin_unit_id=admin_unit_id, statistics=stats, method=method, model_version_id=mv.id, status="READY", is_demo=scene.is_demo)
        db.add(product)
        scene.processing_status = "READY"
        db.flush()
        rec = evidence_service.create_recommendation(db, kind="rs_product", title=f"{product_type.upper()} for scene {scene.scene_id}", statement=f"Derived {product_type.upper()} product using {method}. Values are MODELLED estimates from reflectance data.", created_by=user_id, confidence=0.6 if not scene.is_demo else 0.3, confidence_basis="index computation is deterministic; confidence reflects lack of calibration/cloud masking", limitations=mv.limitations, model_version_id=mv.id, is_demo=scene.is_demo)
        evidence_service.add_evidence(db, rec, source_type=NodeType.RS_PRODUCT, source_id=product.id, label=f"{product_type.upper()} statistics", excerpt=json.dumps(stats)[:600], value_kind="MODELLED")
        db.commit()
        return product
    except Exception as exc:
        db.rollback()
        scene = db.get(RSScene, scene.id)
        scene.processing_status = "FAILED"
        scene.processing_error = str(exc)[:1000]
        db.commit()
        raise


def compare_scenes(db: Session, before: RSScene, after: RSScene, user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    conn = get_connector()
    result = change_detection(conn.load_bands(before), conn.load_bands(after))
    mv = _model_version(db)
    product = RSProduct(scene_id=after.id, product_type="change", statistics={**result, "before_scene": before.scene_id}, method=result["method"], model_version_id=mv.id, status="READY", is_demo=before.is_demo or after.is_demo)
    db.add(product)
    db.flush()
    rec = evidence_service.create_recommendation(db, kind="rs_change", title=f"Land-cover change {before.acquisition_date} → {after.acquisition_date}", statement=f"Vegetation loss {result['vegetation_loss_km2']} km², gain {result['vegetation_gain_km2']} km², urban expansion {result['urban_expansion_km2']} km² (MODELLED).", created_by=user_id, confidence=0.5 if not product.is_demo else 0.3, confidence_basis="deterministic index differencing; no field validation", limitations=mv.limitations, model_version_id=mv.id, is_demo=product.is_demo)
    evidence_service.add_evidence(db, rec, source_type=NodeType.RS_PRODUCT, source_id=product.id, label="Change detection product", excerpt=json.dumps(result)[:600], value_kind="MODELLED")
    db.commit()
    return {"product_id": str(product.id), "recommendation_id": str(rec.id), "before": before.scene_id, "after": after.scene_id, "is_demo": product.is_demo, **result, "value_kind": "MODELLED"}


def scene_dict(s: RSScene, db: Session) -> Dict[str, Any]:
    bounds = db.scalar(select(func.ST_AsGeoJSON(RSScene.bounds)).where(RSScene.id == s.id)) if s.bounds is not None else None
    return {"id": str(s.id), "source": s.source, "scene_id": s.scene_id, "acquisition_date": s.acquisition_date.isoformat() if s.acquisition_date else None, "resolution_m": s.resolution_m, "cloud_cover": s.cloud_cover, "bounds": json.loads(bounds) if bounds else None, "bands": s.bands, "processing_status": s.processing_status, "processing_error": s.processing_error, "provenance": s.provenance, "is_demo": s.is_demo, "products": [{"id": str(p.id), "type": p.product_type, "status": p.status, "statistics": p.statistics, "method": p.method, "is_demo": p.is_demo, "created_at": p.created_at.isoformat()} for p in s.products]}
