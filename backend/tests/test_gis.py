import pytest

from tests.conftest import square


def test_admin_units_and_geojson(client, demo_geography):
    d1 = demo_geography["d1"]
    r = client.get("/api/v1/gis/admin-units", params={"level": "district"})
    assert r.status_code == 200 and any(u["code"] == "T-D-A" for u in r.json()["items"])
    r = client.get(f"/api/v1/gis/admin-units/{d1.id}")
    feat = r.json()
    assert feat["type"] == "Feature" and feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert feat["properties"]["area_km2"] > 20000 and feat["properties"]["path"][0]["name"] == "Test State"
    r = client.get("/api/v1/gis/admin-units/search", params={"q": "District A"})
    assert r.json()["items"][0]["name"] == "Test District A"
    r = client.get("/api/v1/gis/admin-units/geojson", params={"parent_id": str(demo_geography["state"].id)})
    assert len(r.json()["features"]) == 2


def test_layer_features_statistics_compare(client, demo_geography):
    layer = demo_geography["layer"]
    r = client.get(f"/api/v1/gis/layers/{layer.id}/features", params={"bbox": "76,30,78,32", "limit": 10})
    assert r.status_code == 200 and len(r.json()["features"]) == 10
    assert all(f["properties"]["admin_unit_id"] for f in r.json()["features"]), "features assigned to districts by centroid"
    r = client.get(f"/api/v1/gis/layers/{layer.id}/features", params={"class_value": "forest"})
    assert all(f["properties"]["class"] == "forest" for f in r.json()["features"])
    stats = client.get(f"/api/v1/gis/layers/{layer.id}/statistics").json()
    assert stats["feature_count"] == 40 and stats["total_area_km2"] > 0
    assert abs(sum(c["share_pct"] for c in stats["classes"]) - 100) < 0.5
    cmp = client.get(f"/api/v1/gis/layers/{layer.id}/compare", params={"unit_ids": f"{demo_geography['d1'].id},{demo_geography['d2'].id}"}).json()
    assert len(cmp["comparison"]) == 2 and all(c["total_area_km2"] >= 0 for c in cmp["comparison"])


def test_spatial_operations(client, gis_analyst, demo_geography):
    gh, _ = gis_analyst
    layer, d1 = demo_geography["layer"], demo_geography["d1"]
    area = client.post("/api/v1/gis/ops/area", json={"admin_unit_id": str(d1.id)}, headers=gh).json()
    assert 20000 < area["area_km2"] < 24000 and area["valid"] is True and area["run_id"]
    inter = client.post("/api/v1/gis/ops/intersection", json={"layer_a": str(layer.id), "admin_unit_id": str(d1.id)}, headers=gh).json()
    assert inter["total_area_km2"] > 0 and inter["geometry"] is not None
    prox = client.post("/api/v1/gis/ops/proximity", json={"layer_id": str(layer.id), "lon": 76.5, "lat": 31.0, "radius_m": 60000, "limit": 5}, headers=gh).json()
    assert prox["count"] >= 1 and prox["features"] == sorted(prox["features"], key=lambda f: f["distance_m"])
    agg = client.post("/api/v1/gis/ops/aggregate", json={"layer_id": str(layer.id), "level": "district", "metric": "area"}, headers=gh).json()
    assert agg["units"] == 2 and all("share_of_unit_pct" in u for u in agg["items"])
    hot = client.post("/api/v1/gis/ops/hotspot", json={"layer_id": str(layer.id), "cell_deg": 0.5}, headers=gh).json()
    assert hot["cells"] and hot["value_kind"] == "MODELLED" and abs(sum(c["z"] for c in hot["cells"])) < 0.05
    sel = client.post("/api/v1/gis/ops/boundary-select", json={"geometry": square(76.5, 30.5, 1.0, 1.0), "level": "district"}, headers=gh).json()
    assert sel["count"] == 2 and all(0 < i["overlap_pct"] <= 100 for i in sel["items"])
    aff = client.post("/api/v1/gis/ops/affected-area", json={"geometry": {"type": "Point", "coordinates": [76.5, 31.0]}, "buffer_m": 30000, "layer_ids": [str(layer.id)]}, headers=gh).json()
    assert 2700 < aff["zone_area_km2"] < 2900 and aff["admin_units_affected"] >= 1 and aff["impacts"][0]["layer"]["id"] == str(layer.id)
    runs = client.get("/api/v1/gis/ops/runs", headers=gh).json()["items"]
    assert {r["operation"] for r in runs} >= {"area", "intersection", "proximity", "aggregate", "hotspot", "boundary_select", "affected_area"}


def test_public_cannot_run_analysis_ops(client, public_user, demo_geography):
    ph, _ = public_user
    r = client.post("/api/v1/gis/ops/hotspot", json={"layer_id": str(demo_geography["layer"].id)}, headers=ph)
    assert r.status_code == 403


def test_remote_sensing_demo_pipeline(client, gis_analyst):
    gh, _ = gis_analyst
    st = client.get("/api/v1/remote-sensing/status", headers=gh).json()
    assert st["mode"] == "demo"
    r = client.post("/api/v1/remote-sensing/scenes/search", json={"bbox": [76, 30, 77, 31], "start": "2023-01-01", "end": "2023-04-30", "limit": 3}, headers=gh)
    assert r.status_code == 201
    scenes = r.json()["items"]
    assert len(scenes) >= 2 and all(s["is_demo"] for s in scenes)
    p = client.post(f"/api/v1/remote-sensing/scenes/{scenes[0]['id']}/products", params={"product_type": "ndvi"}, headers=gh).json()
    assert -1 <= p["statistics"]["min"] <= p["statistics"]["mean"] <= p["statistics"]["max"] <= 1 and p["value_kind"] == "MODELLED"
    l = client.post(f"/api/v1/remote-sensing/scenes/{scenes[0]['id']}/products", params={"product_type": "lulc"}, headers=gh).json()
    assert abs(sum(l["statistics"]["share_pct"].values()) - 100) < 0.1
    ch = client.post("/api/v1/remote-sensing/change", params={"before_id": scenes[0]["id"], "after_id": scenes[-1]["id"]}, headers=gh).json()
    assert "vegetation_loss_km2" in ch and ch["recommendation_id"]
    tr = client.get(f"/api/v1/evidence/{ch['recommendation_id']}/trace", headers=gh).json()
    assert {"rs_product", "model_version"} <= {n["type"] for n in tr["nodes"]}
