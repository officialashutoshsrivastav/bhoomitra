from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, require_permissions
from app.audit import service as audit
from app.core.permissions import P
from app.db.database import get_db
from app.gis import remote_sensing as rs
from app.gis import service as gis
from app.models.gis import AdminLevel, GISLayer, LayerCategory, RSScene
from app.models.identity import User
from app.schemas.common import Message
from app.services.document_service import unique_slug

router = APIRouter(prefix="/gis", tags=["gis"])
rs_router = APIRouter(prefix="/remote-sensing", tags=["remote-sensing"])


def _bbox(bbox: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not bbox:
        return None
    parts = [float(p) for p in bbox.split(",")]
    if len(parts) != 4:
        from app.core.exceptions import ValidationFailed

        raise ValidationFailed("bbox must be minLon,minLat,maxLon,maxLat")
    return parts[0], parts[1], parts[2], parts[3]


# ---- admin hierarchy ----
@router.get("/admin-units")
def admin_units(level: Optional[AdminLevel] = None, parent_id: Optional[uuid.UUID] = None, q: Annotated[Optional[str], Query(max_length=100)] = None, limit: Annotated[int, Query(le=2000)] = 500, db: Session = Depends(get_db)):
    return {"items": gis.list_units(db, level, parent_id, q, limit)}


@router.get("/admin-units/search")
def admin_unit_search(q: Annotated[str, Query(min_length=2, max_length=100)], db: Session = Depends(get_db)):
    return {"items": gis.search_locations(db, q)}


@router.get("/admin-units/geojson")
def admin_units_geojson(parent_id: Optional[uuid.UUID] = None, level: Optional[AdminLevel] = None, simplify: Annotated[float, Query(ge=0, le=0.1)] = 0.001, db: Session = Depends(get_db)):
    return gis.children_geojson(db, parent_id, level, simplify)


@router.get("/admin-units/{unit_id}")
def admin_unit(unit_id: uuid.UUID, simplify: Annotated[float, Query(ge=0, le=0.1)] = 0.0, db: Session = Depends(get_db)):
    feat = gis.unit_geojson(db, unit_id, simplify)
    feat["properties"]["path"] = gis.unit_path(db, unit_id)
    return feat


# ---- layers ----
@router.get("/layers")
def layers(category: Optional[LayerCategory] = None, include_demo: bool = True, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    return {"items": gis.list_layers(db, category, public_only=user is None, include_demo=include_demo)}


class LayerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = None
    category: LayerCategory
    geometry_type: str = Field("Polygon", max_length=30)
    dataset_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    source: Optional[str] = Field(None, max_length=255)
    source_license: Optional[str] = Field(None, max_length=120)
    value_field: Optional[str] = Field(None, max_length=80)
    class_field: Optional[str] = Field(None, max_length=80)
    legend: Optional[Dict[str, Any]] = None
    style: Optional[Dict[str, Any]] = None
    temporal_start: Optional[date] = None
    temporal_end: Optional[date] = None
    is_public: bool = True


@router.post("/layers", status_code=status.HTTP_201_CREATED)
def create_layer(payload: LayerCreate, request: Request, user: User = Depends(require_permissions(P.GIS_MANAGE)), db: Session = Depends(get_db)):
    layer = GISLayer(**payload.model_dump(), slug=unique_slug(db, GISLayer, payload.name), created_by=user.id)
    db.add(layer)
    db.flush()
    audit.record(db, "gis.layer_create", user=user, resource_type="gis_layer", resource_id=layer.id, request=request)
    db.commit()
    return gis.layer_summary(layer)


class FeatureCollectionIn(BaseModel):
    type: str = "FeatureCollection"
    features: List[Dict[str, Any]] = Field(max_length=20000)


@router.post("/layers/{layer_id}/features", response_model=Message, status_code=status.HTTP_201_CREATED)
def add_features(layer_id: uuid.UUID, payload: FeatureCollectionIn, request: Request, user: User = Depends(require_permissions(P.GIS_MANAGE)), db: Session = Depends(get_db)):
    layer = gis.get_layer(db, layer_id)
    n = gis.add_features(db, layer, payload.model_dump())
    audit.record(db, "gis.features_add", user=user, resource_type="gis_layer", resource_id=layer.id, detail={"added": n}, request=request)
    db.commit()
    return Message(message=f"{n} features added", detail={"feature_count": layer.feature_count})


@router.get("/layers/{layer_id}")
def layer_detail(layer_id: uuid.UUID, db: Session = Depends(get_db)):
    return gis.layer_summary(gis.get_layer(db, layer_id))


@router.get("/layers/{layer_id}/features")
def layer_features(layer_id: uuid.UUID, bbox: Optional[str] = None, admin_unit_id: Optional[uuid.UUID] = None, class_value: Optional[str] = None, at: Optional[date] = None, limit: Annotated[int, Query(le=20000)] = 5000, simplify: Annotated[float, Query(ge=0, le=0.05)] = 0.0005, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    layer = gis.get_layer(db, layer_id)
    if not layer.is_public and user is None:
        from app.core.exceptions import AuthError

        raise AuthError("Authentication required for this layer")
    return gis.layer_features(db, layer, bbox=_bbox(bbox), admin_unit_id=admin_unit_id, class_value=class_value, at=at, limit=limit, simplify=simplify)


@router.get("/layers/{layer_id}/statistics")
def layer_statistics(layer_id: uuid.UUID, admin_unit_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db)):
    return gis.layer_statistics(db, gis.get_layer(db, layer_id), admin_unit_id)


@router.get("/layers/{layer_id}/temporal")
def layer_temporal(layer_id: uuid.UUID, admin_unit_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db)):
    return gis.temporal_summary(db, gis.get_layer(db, layer_id), admin_unit_id)


@router.get("/layers/{layer_id}/compare")
def layer_compare(layer_id: uuid.UUID, unit_ids: Annotated[str, Query(description="comma separated admin unit ids")], db: Session = Depends(get_db)):
    ids = [uuid.UUID(u.strip()) for u in unit_ids.split(",") if u.strip()][:10]
    return gis.compare_geographies(db, gis.get_layer(db, layer_id), ids)


@router.get("/features/{feature_id}")
def feature(feature_id: uuid.UUID, db: Session = Depends(get_db)):
    return gis.feature_detail(db, feature_id)


# ---- spatial operations ----
class IntersectionIn(BaseModel):
    layer_a: uuid.UUID
    layer_b: Optional[uuid.UUID] = None
    admin_unit_id: Optional[uuid.UUID] = None
    geometry: Optional[Dict[str, Any]] = None


class AreaIn(BaseModel):
    geometry: Optional[Dict[str, Any]] = None
    admin_unit_id: Optional[uuid.UUID] = None
    feature_id: Optional[uuid.UUID] = None


class ProximityIn(BaseModel):
    layer_id: uuid.UUID
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    radius_m: float = Field(5000, gt=0, le=500000)
    limit: int = Field(50, ge=1, le=500)


class AggregateIn(BaseModel):
    layer_id: uuid.UUID
    level: AdminLevel = AdminLevel.DISTRICT
    parent_id: Optional[uuid.UUID] = None
    metric: str = Field("area", pattern="^(area|count|sum|mean)$")


class HotspotIn(BaseModel):
    layer_id: uuid.UUID
    cell_deg: float = Field(0.25, gt=0, le=5)
    admin_unit_id: Optional[uuid.UUID] = None


class BoundarySelectIn(BaseModel):
    geometry: Dict[str, Any]
    level: AdminLevel = AdminLevel.DISTRICT
    mode: str = Field("intersects", pattern="^(intersects|within)$")


class AffectedAreaIn(BaseModel):
    geometry: Dict[str, Any]
    buffer_m: float = Field(1000, ge=0, le=200000)
    layer_ids: List[uuid.UUID] = Field(min_length=1, max_length=10)


@router.post("/ops/intersection")
def intersection(payload: IntersectionIn, user: User = Depends(require_permissions(P.GIS_ANALYZE)), db: Session = Depends(get_db)):
    return gis.op_intersection(db, payload.layer_a, payload.layer_b, payload.admin_unit_id, payload.geometry, user.id)


@router.post("/ops/area")
def area(payload: AreaIn, user: User = Depends(require_permissions(P.GIS_VIEW)), db: Session = Depends(get_db)):
    return gis.op_area(db, payload.geometry, payload.admin_unit_id, payload.feature_id, user.id)


@router.post("/ops/proximity")
def proximity(payload: ProximityIn, user: User = Depends(require_permissions(P.GIS_VIEW)), db: Session = Depends(get_db)):
    return gis.op_proximity(db, payload.layer_id, payload.lon, payload.lat, payload.radius_m, payload.limit, user.id)


@router.post("/ops/aggregate")
def aggregate(payload: AggregateIn, user: User = Depends(require_permissions(P.GIS_ANALYZE)), db: Session = Depends(get_db)):
    return gis.op_aggregate(db, payload.layer_id, payload.level, payload.parent_id, payload.metric, user.id)


@router.post("/ops/hotspot")
def hotspot(payload: HotspotIn, user: User = Depends(require_permissions(P.GIS_ANALYZE)), db: Session = Depends(get_db)):
    return gis.op_hotspot(db, payload.layer_id, payload.cell_deg, payload.admin_unit_id, user.id)


@router.post("/ops/boundary-select")
def boundary_select(payload: BoundarySelectIn, user: User = Depends(require_permissions(P.GIS_VIEW)), db: Session = Depends(get_db)):
    return gis.op_boundary_select(db, payload.geometry, payload.level, payload.mode, user.id)


@router.post("/ops/affected-area")
def affected_area(payload: AffectedAreaIn, user: User = Depends(require_permissions(P.GIS_ANALYZE)), db: Session = Depends(get_db)):
    return gis.op_affected_area(db, payload.geometry, payload.buffer_m, payload.layer_ids, user.id)


@router.get("/ops/runs")
def runs(limit: Annotated[int, Query(le=200)] = 50, user: User = Depends(require_permissions(P.GIS_VIEW)), db: Session = Depends(get_db)):
    return {"items": gis.list_runs(db, limit)}


# ---- remote sensing ----
class SceneSearchIn(BaseModel):
    bbox: List[float] = Field(min_length=4, max_length=4)
    start: date
    end: date
    max_cloud: float = Field(30, ge=0, le=100)
    limit: int = Field(6, ge=1, le=50)


@rs_router.get("/status")
def rs_status(user: User = Depends(require_permissions(P.RS_VIEW))):
    conn = rs.get_connector()
    return {"connector": conn.name, "mode": conn.mode, "note": "Demo / Synthetic Data — configure STAC_ENDPOINT for live catalogues" if conn.mode == "demo" else "Live STAC catalogue configured; raster loading requires rasterio + network"}


@rs_router.post("/scenes/search", status_code=status.HTTP_201_CREATED)
def search_scenes(payload: SceneSearchIn, request: Request, user: User = Depends(require_permissions(P.RS_MANAGE)), db: Session = Depends(get_db)):
    scenes = rs.register_scenes(db, tuple(payload.bbox), payload.start, payload.end, payload.max_cloud, payload.limit)
    audit.record(db, "rs.scenes_registered", user=user, resource_type="rs_scene", detail={"count": len(scenes)}, request=request, commit=True)
    return {"items": [rs.scene_dict(s, db) for s in scenes], "connector": rs.get_connector().name}


@rs_router.get("/scenes")
def list_scenes(limit: Annotated[int, Query(le=200)] = 50, user: User = Depends(require_permissions(P.RS_VIEW)), db: Session = Depends(get_db)):
    rows = db.scalars(select(RSScene).order_by(RSScene.acquisition_date.desc().nullslast()).limit(limit)).all()
    return {"items": [rs.scene_dict(s, db) for s in rows]}


@rs_router.get("/scenes/{scene_id}")
def scene(scene_id: uuid.UUID, user: User = Depends(require_permissions(P.RS_VIEW)), db: Session = Depends(get_db)):
    return rs.scene_dict(rs.get_scene(db, scene_id), db)


@rs_router.post("/scenes/{scene_id}/products")
def derive(scene_id: uuid.UUID, request: Request, product_type: Annotated[str, Query(pattern="^(ndvi|ndwi|ndbi|lulc)$")], admin_unit_id: Optional[uuid.UUID] = None, user: User = Depends(require_permissions(P.RS_MANAGE)), db: Session = Depends(get_db)):
    p = rs.derive_product(db, rs.get_scene(db, scene_id), product_type, admin_unit_id, user.id)
    audit.record(db, "rs.product_derived", user=user, resource_type="rs_product", resource_id=p.id, detail={"type": product_type}, request=request, commit=True)
    return {"id": str(p.id), "type": p.product_type, "statistics": p.statistics, "method": p.method, "is_demo": p.is_demo, "value_kind": "MODELLED"}


@rs_router.post("/change")
def change(before_id: uuid.UUID, after_id: uuid.UUID, user: User = Depends(require_permissions(P.RS_MANAGE)), db: Session = Depends(get_db)):
    return rs.compare_scenes(db, rs.get_scene(db, before_id), rs.get_scene(db, after_id), user.id)
