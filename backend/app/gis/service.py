from __future__ import annotations

import json
import math
import time
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from geoalchemy2 import functions as gf
from geoalchemy2.shape import to_shape
from sqlalchemy import Float, and_, cast, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.gis import AdminLevel, AdminUnit, GISFeature, GISLayer, LayerCategory, SpatialAnalysisRun

GEOG = 4326
METRIC_SRID = 7755  # India-wide LCC (WGS84 / India NSF LCC) for area/length in metres


def _geojson(geom_col):
    return func.ST_AsGeoJSON(geom_col, 6)


def _feature(props: Dict[str, Any], geometry_json: Optional[str], fid: Any) -> Dict[str, Any]:
    return {"type": "Feature", "id": str(fid), "properties": props, "geometry": json.loads(geometry_json) if geometry_json else None}


def _parse_geometry(geojson: Dict[str, Any]) -> str:
    if not isinstance(geojson, dict) or "type" not in geojson:
        raise ValidationFailed("geometry must be a GeoJSON geometry object")
    if geojson.get("type") == "Feature":
        geojson = geojson.get("geometry") or {}
    return json.dumps(geojson)


def _geom_from_geojson(geojson: Dict[str, Any]):
    return func.ST_SetSRID(func.ST_GeomFromGeoJSON(_parse_geometry(geojson)), GEOG)


# ---------------------------------------------------------------------------
# Administrative hierarchy
# ---------------------------------------------------------------------------
def list_units(db: Session, level: Optional[AdminLevel], parent_id: Optional[uuid.UUID], q: Optional[str], limit: int = 500) -> List[Dict[str, Any]]:
    stmt = select(AdminUnit.id, AdminUnit.name, AdminUnit.code, AdminUnit.level, AdminUnit.parent_id, AdminUnit.centroid_lat, AdminUnit.centroid_lon, AdminUnit.area_km2, AdminUnit.is_demo, AdminUnit.source)
    if level:
        stmt = stmt.where(AdminUnit.level == level)
    if parent_id:
        stmt = stmt.where(AdminUnit.parent_id == parent_id)
    if q:
        stmt = stmt.where(or_(AdminUnit.name.ilike(f"%{q}%"), AdminUnit.code.ilike(f"{q}%")))
    rows = db.execute(stmt.order_by(AdminUnit.name).limit(limit)).all()
    return [{"id": str(r.id), "name": r.name, "code": r.code, "level": r.level.value, "parent_id": str(r.parent_id) if r.parent_id else None, "centroid": [r.centroid_lon, r.centroid_lat] if r.centroid_lat is not None else None, "area_km2": r.area_km2, "is_demo": r.is_demo, "source": r.source} for r in rows]


def unit_geojson(db: Session, unit_id: uuid.UUID, simplify: float = 0.0) -> Dict[str, Any]:
    geom = AdminUnit.geom if simplify <= 0 else func.ST_SimplifyPreserveTopology(AdminUnit.geom, simplify)
    row = db.execute(select(AdminUnit, _geojson(geom)).where(AdminUnit.id == unit_id)).first()
    if not row:
        raise NotFoundError("Administrative unit not found")
    u, gj = row
    return _feature({"name": u.name, "code": u.code, "level": u.level.value, "parent_id": str(u.parent_id) if u.parent_id else None, "area_km2": u.area_km2, "is_demo": u.is_demo, "source": u.source, "license": u.source_license}, gj, u.id)


def children_geojson(db: Session, parent_id: Optional[uuid.UUID], level: Optional[AdminLevel], simplify: float = 0.001) -> Dict[str, Any]:
    geom = func.ST_SimplifyPreserveTopology(AdminUnit.geom, simplify) if simplify > 0 else AdminUnit.geom
    stmt = select(AdminUnit, _geojson(geom))
    if parent_id:
        stmt = stmt.where(AdminUnit.parent_id == parent_id)
    if level:
        stmt = stmt.where(AdminUnit.level == level)
    if not parent_id and not level:
        stmt = stmt.where(AdminUnit.level == AdminLevel.STATE)
    feats = [_feature({"name": u.name, "code": u.code, "level": u.level.value, "area_km2": u.area_km2, "is_demo": u.is_demo}, gj, u.id) for u, gj in db.execute(stmt.order_by(AdminUnit.name).limit(2000)).all()]
    return {"type": "FeatureCollection", "features": feats}


def unit_path(db: Session, unit_id: uuid.UUID) -> List[Dict[str, Any]]:
    path = []
    cur = db.get(AdminUnit, unit_id)
    while cur is not None and len(path) < 6:
        path.insert(0, {"id": str(cur.id), "name": cur.name, "level": cur.level.value})
        cur = db.get(AdminUnit, cur.parent_id) if cur.parent_id else None
    return path


def search_locations(db: Session, q: str, limit: int = 10) -> List[Dict[str, Any]]:
    sim = func.similarity(AdminUnit.name, q)
    rows = db.execute(select(AdminUnit, sim).where(or_(AdminUnit.name.ilike(f"%{q}%"), sim > 0.3)).order_by(sim.desc(), AdminUnit.level).limit(limit)).all()
    return [{"id": str(u.id), "name": u.name, "level": u.level.value, "code": u.code, "centroid": [u.centroid_lon, u.centroid_lat] if u.centroid_lat is not None else None, "path": " › ".join(p["name"] for p in unit_path(db, u.id)), "score": float(s or 0)} for u, s in rows]


def refresh_unit_metrics(db: Session, unit: AdminUnit) -> None:
    row = db.execute(select(func.ST_Y(func.ST_Centroid(AdminUnit.geom)), func.ST_X(func.ST_Centroid(AdminUnit.geom)), func.ST_Area(cast(AdminUnit.geom, __import__("geoalchemy2").Geography)) / 1e6).where(AdminUnit.id == unit.id)).first()
    if row and row[0] is not None:
        unit.centroid_lat, unit.centroid_lon, unit.area_km2 = float(row[0]), float(row[1]), round(float(row[2]), 3)


# ---------------------------------------------------------------------------
# Layers & features
# ---------------------------------------------------------------------------
def list_layers(db: Session, category: Optional[LayerCategory], public_only: bool, include_demo: bool = True) -> List[Dict[str, Any]]:
    stmt = select(GISLayer)
    if category:
        stmt = stmt.where(GISLayer.category == category)
    if public_only:
        stmt = stmt.where(GISLayer.is_public.is_(True))
    if not include_demo:
        stmt = stmt.where(GISLayer.is_demo.is_(False))
    return [layer_summary(l) for l in db.scalars(stmt.order_by(GISLayer.category, GISLayer.name)).all()]


def layer_summary(l: GISLayer) -> Dict[str, Any]:
    return {"id": str(l.id), "name": l.name, "slug": l.slug, "description": l.description, "category": l.category.value, "geometry_type": l.geometry_type, "legend": l.legend, "style": l.style, "value_field": l.value_field, "class_field": l.class_field, "temporal_start": l.temporal_start.isoformat() if l.temporal_start else None, "temporal_end": l.temporal_end.isoformat() if l.temporal_end else None, "source": l.source, "license": l.source_license, "feature_count": l.feature_count, "is_public": l.is_public, "is_demo": l.is_demo, "dataset_id": str(l.dataset_id) if l.dataset_id else None}


def get_layer(db: Session, layer_id: uuid.UUID) -> GISLayer:
    l = db.get(GISLayer, layer_id)
    if not l:
        raise NotFoundError("Layer not found")
    return l


def layer_features(db: Session, layer: GISLayer, *, bbox: Optional[Tuple[float, float, float, float]], admin_unit_id: Optional[uuid.UUID], class_value: Optional[str], at: Optional[date], limit: int = 5000, simplify: float = 0.0005) -> Dict[str, Any]:
    geom = func.ST_SimplifyPreserveTopology(GISFeature.geom, simplify) if simplify > 0 and layer.geometry_type.lower() not in ("point", "multipoint") else GISFeature.geom
    stmt = select(GISFeature, _geojson(geom)).where(GISFeature.layer_id == layer.id)
    if bbox:
        stmt = stmt.where(func.ST_Intersects(GISFeature.geom, func.ST_MakeEnvelope(*bbox, GEOG)))
    if admin_unit_id:
        unit_geom = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        stmt = stmt.where(func.ST_Intersects(GISFeature.geom, unit_geom))
    if class_value:
        stmt = stmt.where(GISFeature.class_value == class_value)
    if at:
        stmt = stmt.where(or_(GISFeature.valid_from.is_(None), GISFeature.valid_from <= at), or_(GISFeature.valid_to.is_(None), GISFeature.valid_to >= at))
    feats = []
    for f, gj in db.execute(stmt.limit(limit)).all():
        props = {"name": f.name, "class": f.class_value, "value": f.numeric_value, "valid_from": f.valid_from.isoformat() if f.valid_from else None, "valid_to": f.valid_to.isoformat() if f.valid_to else None, "admin_unit_id": str(f.admin_unit_id) if f.admin_unit_id else None, **(f.properties or {})}
        feats.append(_feature(props, gj, f.id))
    return {"type": "FeatureCollection", "layer": layer_summary(layer), "features": feats}


def feature_detail(db: Session, feature_id: uuid.UUID) -> Dict[str, Any]:
    row = db.execute(select(GISFeature, _geojson(GISFeature.geom), func.ST_Area(cast(GISFeature.geom, __import__("geoalchemy2").Geography)) / 1e6, func.ST_Y(func.ST_Centroid(GISFeature.geom)), func.ST_X(func.ST_Centroid(GISFeature.geom))).where(GISFeature.id == feature_id)).first()
    if not row:
        raise NotFoundError("Feature not found")
    f, gj, area, lat, lon = row
    layer = db.get(GISLayer, f.layer_id)
    unit = db.get(AdminUnit, f.admin_unit_id) if f.admin_unit_id else None
    return {**_feature({"name": f.name, "class": f.class_value, "value": f.numeric_value, "area_km2": round(float(area or 0), 4), "centroid": [lon, lat], "layer": layer_summary(layer) if layer else None, "admin_unit": {"id": str(unit.id), "name": unit.name, "level": unit.level.value} if unit else None, "valid_from": f.valid_from.isoformat() if f.valid_from else None, "valid_to": f.valid_to.isoformat() if f.valid_to else None, **(f.properties or {})}, gj, f.id)}


def add_features(db: Session, layer: GISLayer, feature_collection: Dict[str, Any], is_demo: bool = False) -> int:
    feats = feature_collection.get("features") or []
    n = 0
    for ft in feats:
        geom = ft.get("geometry")
        if not geom:
            continue
        props = dict(ft.get("properties") or {})
        class_value = props.pop(layer.class_field, None) if layer.class_field else props.pop("class", None)
        numeric = props.pop(layer.value_field, None) if layer.value_field else props.pop("value", None)
        try:
            numeric = float(numeric) if numeric is not None else None
        except (TypeError, ValueError):
            numeric = None
        vf = props.pop("valid_from", None)
        vt = props.pop("valid_to", None)
        db.add(GISFeature(layer_id=layer.id, name=props.pop("name", None), class_value=str(class_value) if class_value is not None else None, numeric_value=numeric, properties=props or None, geom=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geom)), GEOG), valid_from=date.fromisoformat(vf) if vf else None, valid_to=date.fromisoformat(vt) if vt else None))
        n += 1
    db.flush()
    layer.feature_count = db.scalar(select(func.count(GISFeature.id)).where(GISFeature.layer_id == layer.id)) or 0
    # assign admin unit by centroid containment (district level preferred)
    db.execute(text("""
        UPDATE gis_features f SET admin_unit_id = a.id
        FROM admin_units a
        WHERE f.layer_id = :lid AND f.admin_unit_id IS NULL AND a.level = 'DISTRICT' AND ST_Contains(a.geom, ST_Centroid(f.geom))
    """), {"lid": str(layer.id)})
    db.flush()
    return n


# ---------------------------------------------------------------------------
# Spatial statistics & thematic summaries
# ---------------------------------------------------------------------------
def layer_statistics(db: Session, layer: GISLayer, admin_unit_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    from geoalchemy2 import Geography

    geom = GISFeature.geom
    conds = [GISFeature.layer_id == layer.id]
    if admin_unit_id:
        unit_geom = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        geom = func.ST_Intersection(GISFeature.geom, unit_geom)
        conds.append(func.ST_Intersects(GISFeature.geom, unit_geom))
    area_expr = func.sum(func.ST_Area(cast(geom, Geography))) / 1e6
    rows = db.execute(select(GISFeature.class_value, func.count(GISFeature.id), area_expr, func.avg(GISFeature.numeric_value), func.min(GISFeature.numeric_value), func.max(GISFeature.numeric_value)).where(*conds).group_by(GISFeature.class_value).order_by(area_expr.desc())).all()
    total_area = sum(float(r[2] or 0) for r in rows)
    classes = [{"class": r[0], "count": int(r[1]), "area_km2": round(float(r[2] or 0), 3), "share_pct": round(100 * float(r[2] or 0) / total_area, 2) if total_area else None, "mean_value": float(r[3]) if r[3] is not None else None, "min_value": float(r[4]) if r[4] is not None else None, "max_value": float(r[5]) if r[5] is not None else None} for r in rows]
    return {"layer": layer_summary(layer), "admin_unit_id": str(admin_unit_id) if admin_unit_id else None, "total_area_km2": round(total_area, 3), "feature_count": sum(c["count"] for c in classes), "classes": classes, "value_kind": "OBSERVED" if not layer.is_demo else "OBSERVED (Demo / Synthetic Data)"}


def compare_geographies(db: Session, layer: GISLayer, unit_ids: List[uuid.UUID]) -> Dict[str, Any]:
    return {"layer": layer_summary(layer), "comparison": [{"admin_unit": {"id": str(u.id), "name": u.name, "level": u.level.value}, **{k: v for k, v in layer_statistics(db, layer, u.id).items() if k in ("total_area_km2", "feature_count", "classes")}} for u in [db.get(AdminUnit, i) for i in unit_ids] if u]}


def temporal_summary(db: Session, layer: GISLayer, admin_unit_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    from geoalchemy2 import Geography

    conds = [GISFeature.layer_id == layer.id, GISFeature.valid_from.is_not(None)]
    if admin_unit_id:
        unit_geom = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        conds.append(func.ST_Intersects(GISFeature.geom, unit_geom))
    rows = db.execute(select(func.extract("year", GISFeature.valid_from).label("year"), GISFeature.class_value, func.sum(func.ST_Area(cast(GISFeature.geom, Geography))) / 1e6, func.avg(GISFeature.numeric_value)).where(*conds).group_by("year", GISFeature.class_value).order_by("year")).all()
    series: Dict[str, List[Dict[str, Any]]] = {}
    for year, cls, area, mean in rows:
        series.setdefault(cls or "all", []).append({"year": int(year), "area_km2": round(float(area or 0), 3), "mean_value": float(mean) if mean is not None else None})
    return {"layer": layer_summary(layer), "series": series}


# ---------------------------------------------------------------------------
# Spatial operations (all executed in PostGIS)
# ---------------------------------------------------------------------------
def _record(db: Session, operation: str, params: Dict[str, Any], summary: Dict[str, Any], t0: float, user_id: Optional[uuid.UUID], result_geojson: Optional[str] = None) -> str:
    run = SpatialAnalysisRun(operation=operation, parameters=params, result_summary=summary, duration_ms=int((time.perf_counter() - t0) * 1000), created_by=user_id)
    if result_geojson:
        run.result_geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(result_geojson), GEOG)
    db.add(run)
    db.commit()
    return str(run.id)


def _area_geom_expr(geom):
    from geoalchemy2 import Geography

    return func.ST_Area(cast(geom, Geography)) / 1e6


def op_intersection(db: Session, layer_a: uuid.UUID, layer_b: Optional[uuid.UUID], admin_unit_id: Optional[uuid.UUID], geometry: Optional[Dict[str, Any]], user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    la = get_layer(db, layer_a)
    if geometry is not None:
        other = _geom_from_geojson(geometry)
        other_label = "custom_geometry"
    elif admin_unit_id:
        other = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        other_label = f"admin_unit:{admin_unit_id}"
    elif layer_b:
        lb = get_layer(db, layer_b)
        other = select(func.ST_Union(GISFeature.geom)).where(GISFeature.layer_id == lb.id).scalar_subquery()
        other_label = f"layer:{lb.slug}"
    else:
        raise ValidationFailed("Provide layer_b, admin_unit_id or geometry")
    inter = func.ST_Intersection(GISFeature.geom, other)
    rows = db.execute(select(GISFeature.class_value, func.count(GISFeature.id), func.sum(_area_geom_expr(inter))).where(GISFeature.layer_id == la.id, func.ST_Intersects(GISFeature.geom, other)).group_by(GISFeature.class_value)).all()
    union_gj = db.scalar(select(func.ST_AsGeoJSON(func.ST_Union(inter), 5)).where(GISFeature.layer_id == la.id, func.ST_Intersects(GISFeature.geom, other)))
    classes = [{"class": c, "features": int(n), "area_km2": round(float(a or 0), 4)} for c, n, a in rows]
    summary = {"layer": la.slug, "with": other_label, "classes": classes, "total_area_km2": round(sum(x["area_km2"] for x in classes), 4)}
    run_id = _record(db, "intersection", {"layer_a": str(layer_a), "layer_b": str(layer_b) if layer_b else None, "admin_unit_id": str(admin_unit_id) if admin_unit_id else None, "custom": geometry is not None}, summary, t0, user_id, union_gj)
    return {"run_id": run_id, **summary, "geometry": json.loads(union_gj) if union_gj else None, "value_kind": "OBSERVED"}


def op_area(db: Session, geometry: Optional[Dict[str, Any]], admin_unit_id: Optional[uuid.UUID], feature_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    from geoalchemy2 import Geography

    t0 = time.perf_counter()
    if geometry is not None:
        g = _geom_from_geojson(geometry)
        label = "custom_geometry"
    elif admin_unit_id:
        g = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        label = f"admin_unit:{admin_unit_id}"
    elif feature_id:
        g = select(GISFeature.geom).where(GISFeature.id == feature_id).scalar_subquery()
        label = f"feature:{feature_id}"
    else:
        raise ValidationFailed("Provide geometry, admin_unit_id or feature_id")
    row = db.execute(select(func.ST_Area(cast(g, Geography)) / 1e6, func.ST_Perimeter(cast(g, Geography)) / 1e3, func.ST_Y(func.ST_Centroid(g)), func.ST_X(func.ST_Centroid(g)), func.ST_IsValid(g))).first()
    summary = {"target": label, "area_km2": round(float(row[0] or 0), 4), "area_ha": round(float(row[0] or 0) * 100, 2), "perimeter_km": round(float(row[1] or 0), 3), "centroid": [row[3], row[2]], "valid": bool(row[4]), "method": "PostGIS geodesic area on WGS84 spheroid"}
    return {"run_id": _record(db, "area", {"target": label}, summary, t0, user_id), **summary, "value_kind": "OBSERVED"}


def op_proximity(db: Session, layer_id: uuid.UUID, lon: float, lat: float, radius_m: float, limit: int, user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    from geoalchemy2 import Geography

    t0 = time.perf_counter()
    layer = get_layer(db, layer_id)
    pt = func.ST_SetSRID(func.ST_MakePoint(lon, lat), GEOG)
    dist = func.ST_Distance(cast(GISFeature.geom, Geography), cast(pt, Geography))
    rows = db.execute(select(GISFeature, dist, _geojson(func.ST_Centroid(GISFeature.geom))).where(GISFeature.layer_id == layer.id, func.ST_DWithin(cast(GISFeature.geom, Geography), cast(pt, Geography), radius_m)).order_by(dist).limit(limit)).all()
    feats = [{"id": str(f.id), "name": f.name, "class": f.class_value, "value": f.numeric_value, "distance_m": round(float(d), 1), "centroid": json.loads(gj)["coordinates"]} for f, d, gj in rows]
    summary = {"layer": layer.slug, "point": [lon, lat], "radius_m": radius_m, "count": len(feats), "nearest_m": feats[0]["distance_m"] if feats else None}
    return {"run_id": _record(db, "proximity", summary, summary, t0, user_id), **summary, "features": feats, "value_kind": "OBSERVED"}


def op_aggregate(db: Session, layer_id: uuid.UUID, level: AdminLevel, parent_id: Optional[uuid.UUID], metric: str, user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    from geoalchemy2 import Geography

    t0 = time.perf_counter()
    layer = get_layer(db, layer_id)
    inter = func.ST_Intersection(GISFeature.geom, AdminUnit.geom)
    if metric == "area":
        agg = func.sum(func.ST_Area(cast(inter, Geography))) / 1e6
    elif metric == "count":
        agg = func.count(GISFeature.id)
    elif metric == "sum":
        agg = func.sum(GISFeature.numeric_value)
    elif metric == "mean":
        agg = func.avg(GISFeature.numeric_value)
    else:
        raise ValidationFailed("metric must be area|count|sum|mean")
    stmt = select(AdminUnit.id, AdminUnit.name, AdminUnit.area_km2, GISFeature.class_value, agg).join(GISFeature, func.ST_Intersects(GISFeature.geom, AdminUnit.geom)).where(AdminUnit.level == level, GISFeature.layer_id == layer.id)
    if parent_id:
        stmt = stmt.where(AdminUnit.parent_id == parent_id)
    rows = db.execute(stmt.group_by(AdminUnit.id, AdminUnit.name, AdminUnit.area_km2, GISFeature.class_value)).all()
    units: Dict[str, Dict[str, Any]] = {}
    for uid, name, uarea, cls, val in rows:
        u = units.setdefault(str(uid), {"admin_unit_id": str(uid), "name": name, "unit_area_km2": uarea, "by_class": {}, "total": 0.0})
        v = float(val or 0)
        u["by_class"][cls or "all"] = round(v, 4)
        u["total"] = round(u["total"] + v, 4)
    out = sorted(units.values(), key=lambda x: -x["total"])
    if metric == "area":
        for u in out:
            u["share_of_unit_pct"] = round(100 * u["total"] / u["unit_area_km2"], 2) if u["unit_area_km2"] else None
    summary = {"layer": layer.slug, "level": level.value, "metric": metric, "units": len(out)}
    return {"run_id": _record(db, "aggregate", summary, summary, t0, user_id), **summary, "items": out, "value_kind": "OBSERVED"}


def op_hotspot(db: Session, layer_id: uuid.UUID, cell_deg: float, admin_unit_id: Optional[uuid.UUID], user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    """Grid-based hotspot detection: bins feature centroids (weighted by numeric
    value when present) into cells, then computes a z-score per cell against the
    grid distribution. Cells with z >= 1.65 (~95%) are flagged hot, <= -1.65 cold."""
    t0 = time.perf_counter()
    layer = get_layer(db, layer_id)
    if cell_deg <= 0 or cell_deg > 5:
        raise ValidationFailed("cell_deg must be between 0 and 5")
    cx = func.floor(func.ST_X(func.ST_Centroid(GISFeature.geom)) / cell_deg)
    cy = func.floor(func.ST_Y(func.ST_Centroid(GISFeature.geom)) / cell_deg)
    weight = func.coalesce(GISFeature.numeric_value, 1.0)
    stmt = select(cx, cy, func.sum(weight), func.count(GISFeature.id)).where(GISFeature.layer_id == layer.id)
    if admin_unit_id:
        unit_geom = select(AdminUnit.geom).where(AdminUnit.id == admin_unit_id).scalar_subquery()
        stmt = stmt.where(func.ST_Intersects(GISFeature.geom, unit_geom))
    rows = db.execute(stmt.group_by(cx, cy)).all()
    if not rows:
        return {"layer": layer.slug, "cells": [], "note": "no features"}
    vals = [float(r[2]) for r in rows]
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    cells = []
    for (x, y, w, n), v in zip(rows, vals):
        z = (v - mean) / sd if sd else 0.0
        cls = "hot" if z >= 1.65 else ("cold" if z <= -1.65 else "neutral")
        x0, y0 = float(x) * cell_deg, float(y) * cell_deg
        cells.append({"cell": [x0, y0, x0 + cell_deg, y0 + cell_deg], "weight": round(v, 3), "count": int(n), "z": round(z, 3), "class": cls, "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + cell_deg, y0], [x0 + cell_deg, y0 + cell_deg], [x0, y0 + cell_deg], [x0, y0]]]}})
    hot = sum(1 for c in cells if c["class"] == "hot")
    summary = {"layer": layer.slug, "cell_deg": cell_deg, "cells": len(cells), "hot_cells": hot, "cold_cells": sum(1 for c in cells if c["class"] == "cold"), "mean_weight": round(mean, 3), "sd": round(sd, 3), "method": "grid z-score (weight = numeric value or 1)"}
    return {"run_id": _record(db, "hotspot", {"layer": str(layer_id), "cell_deg": cell_deg}, summary, t0, user_id), **summary, "cells": sorted(cells, key=lambda c: -c["z"]), "value_kind": "MODELLED"}


def op_boundary_select(db: Session, geometry: Dict[str, Any], level: AdminLevel, mode: str, user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    g = _geom_from_geojson(geometry)
    pred = func.ST_Within(AdminUnit.geom, g) if mode == "within" else func.ST_Intersects(AdminUnit.geom, g)
    rows = db.execute(select(AdminUnit, _area_geom_expr(func.ST_Intersection(AdminUnit.geom, g))).where(AdminUnit.level == level, pred)).all()
    items = [{"id": str(u.id), "name": u.name, "code": u.code, "area_km2": u.area_km2, "overlap_km2": round(float(a or 0), 4), "overlap_pct": round(100 * float(a or 0) / u.area_km2, 2) if u.area_km2 else None} for u, a in rows]
    summary = {"level": level.value, "mode": mode, "count": len(items)}
    return {"run_id": _record(db, "boundary_select", summary, summary, t0, user_id), **summary, "items": items, "value_kind": "OBSERVED"}


def op_affected_area(db: Session, geometry: Dict[str, Any], buffer_m: float, layer_ids: List[uuid.UUID], user_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    """Buffer a hazard/project footprint and report what each layer contains inside it."""
    from geoalchemy2 import Geography

    t0 = time.perf_counter()
    g = _geom_from_geojson(geometry)
    zone = cast(func.ST_Buffer(cast(g, Geography), buffer_m), __import__("geoalchemy2").Geometry) if buffer_m > 0 else g
    zone_area = float(db.scalar(select(func.ST_Area(cast(zone, Geography)) / 1e6)) or 0)
    zone_gj = db.scalar(select(func.ST_AsGeoJSON(zone, 5)))
    impacts = []
    for lid in layer_ids:
        layer = get_layer(db, lid)
        inter = func.ST_Intersection(GISFeature.geom, zone)
        rows = db.execute(select(GISFeature.class_value, func.count(GISFeature.id), func.sum(func.ST_Area(cast(inter, Geography))) / 1e6, func.sum(GISFeature.numeric_value)).where(GISFeature.layer_id == layer.id, func.ST_Intersects(GISFeature.geom, zone)).group_by(GISFeature.class_value)).all()
        classes = [{"class": c, "features": int(n), "area_km2": round(float(a or 0), 4), "value_sum": float(s) if s is not None else None} for c, n, a, s in rows]
        impacts.append({"layer": layer_summary(layer), "classes": classes, "affected_area_km2": round(sum(x["area_km2"] for x in classes), 4), "share_of_zone_pct": round(100 * sum(x["area_km2"] for x in classes) / zone_area, 2) if zone_area else None})
    units = db.execute(select(AdminUnit.id, AdminUnit.name, AdminUnit.level).where(AdminUnit.level.in_([AdminLevel.DISTRICT, AdminLevel.SUBDISTRICT, AdminLevel.VILLAGE]), func.ST_Intersects(AdminUnit.geom, zone)).limit(200)).all()
    summary = {"buffer_m": buffer_m, "zone_area_km2": round(zone_area, 4), "layers": len(impacts), "admin_units_affected": len(units)}
    return {"run_id": _record(db, "affected_area", {"buffer_m": buffer_m, "layers": [str(l) for l in layer_ids]}, summary, t0, user_id, zone_gj), **summary, "zone": json.loads(zone_gj) if zone_gj else None, "impacts": impacts, "admin_units": [{"id": str(i), "name": n, "level": l.value} for i, n, l in units], "value_kind": "OBSERVED"}


def list_runs(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    rows = db.scalars(select(SpatialAnalysisRun).order_by(SpatialAnalysisRun.created_at.desc()).limit(limit)).all()
    return [{"id": str(r.id), "operation": r.operation, "parameters": r.parameters, "summary": r.result_summary, "duration_ms": r.duration_ms, "created_at": r.created_at.isoformat()} for r in rows]
