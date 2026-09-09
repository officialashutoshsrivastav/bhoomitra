import pytest


@pytest.fixture(scope="module")
def dataset(client, gis_analyst, admin_headers, demo_geography):
    gh, _ = gis_analyst
    r = client.post("/api/v1/datasets", json={"name": "Test Cropping Intensity", "category": "agriculture", "geography": "Test State", "access_level": "public", "variables": [{"code": "cropping_intensity", "name": "Cropping intensity", "unit": "%"}]}, headers=gh)
    assert r.status_code == 201, r.text
    ds = r.json()
    rows = ["variable,district,year,value,unit"]
    for yr in range(2015, 2024):
        rows.append(f"cropping_intensity,Test District A,{yr},{100 + 2 * (yr - 2015)},%")
        rows.append(f"cropping_intensity,Test District B,{yr},{120 + 3 * (yr - 2015)},%")
    r = client.post(f"/api/v1/datasets/{ds['id']}/versions", files={"file": ("ci.csv", "\n".join(rows).encode(), "text/csv")}, headers=gh)
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["processing_status"] == "READY" and version["row_count"] == 18
    assert version["schema_snapshot"]["observations_ingested"] == 18
    assert version["schema_snapshot"]["columns"]["value"]["type"] == "number"
    return {"ds": ds, "version": version, "headers": gh}


def test_observations_linked_to_admin_units(client, dataset, demo_geography):
    r = client.get(f"/api/v1/datasets/{dataset['ds']['id']}/observations", params={"variable_code": "cropping_intensity", "page_size": 50}, headers=dataset["headers"])
    assert r.status_code == 200 and r.json()["total"] == 18
    items = r.json()["items"]
    assert all(o["admin_unit_id"] for o in items), "geography names should resolve to admin units"
    assert items[0]["period_start"].endswith("-01-01")


def test_dataset_workflow_and_public_visibility(client, dataset, admin_headers):
    ds = dataset["ds"]
    assert client.get(f"/api/v1/datasets/{ds['id']}").status_code == 404, "draft dataset hidden from public"
    assert client.post(f"/api/v1/datasets/{ds['id']}/submit", headers=dataset["headers"]).json()["status"] == "pending_approval"
    assert client.get("/api/v1/datasets/pending-approval", headers=admin_headers).json()["total"] >= 1
    assert client.post(f"/api/v1/datasets/{ds['id']}/approve", json={"decision": "approve"}, headers=admin_headers).json()["status"] == "approved"
    assert client.post(f"/api/v1/datasets/{ds['id']}/publish", headers=admin_headers).json()["status"] == "published"
    d = client.get(f"/api/v1/datasets/{ds['id']}").json()
    assert d["observation_count"] == 18 and d["versions"][0]["checksum_sha256"]
    r = client.get(f"/api/v1/datasets/{ds['id']}/download")
    assert r.status_code == 200 and r.content.startswith(b"variable,")


def test_trend_is_exact_on_linear_series(client, dataset, demo_geography):
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "trend", "dataset_version_id": dataset["version"]["id"], "variable_code": "cropping_intensity", "admin_unit_id": str(demo_geography["d1"].id)}, headers=dataset["headers"])
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert abs(res["slope_per_year"] - 2.0) < 1e-6 and abs(res["r_squared"] - 1.0) < 1e-9
    assert res["direction"] == "increasing" and res["output_value_kind"] == "MODELLED"
    assert r.json()["recommendation_id"]


def test_forecast_projects_linear_trend(client, dataset, demo_geography):
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "forecast", "dataset_version_id": dataset["version"]["id"], "variable_code": "cropping_intensity", "admin_unit_id": str(demo_geography["d2"].id), "horizon": 3}, headers=dataset["headers"])
    assert r.status_code == 200, r.text
    fc = r.json()["result"]["forecast"]
    assert [p["year"] for p in fc] == [2024, 2025, 2026]
    assert abs(fc[0]["value"] - 147) < 1.0, fc
    assert fc[0]["low"] <= fc[0]["value"] <= fc[0]["high"] and all(p["value_kind"] == "MODELLED" for p in fc)
    assert (fc[2]["high"] - fc[2]["low"]) >= (fc[0]["high"] - fc[0]["low"]), "uncertainty widens with horizon"


def test_compare_anomaly_correlation_risk(client, dataset, demo_geography):
    h = dataset["headers"]
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "compare", "dataset_version_id": dataset["version"]["id"], "variable_code": "cropping_intensity"}, headers=h)
    items = r.json()["result"]["items"]
    assert items[0]["label"] == "Test District B" and items[0]["rank"] == 1 and items[0]["year"] == 2023
    data = [{"label": "X", "year": 2000 + i, "value": 10} for i in range(9)] + [{"label": "X", "year": 2010, "value": 100}]
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "anomaly", "data": data}, headers=h)
    an = r.json()["result"]["anomalies"]
    assert len(an) == 1 and an[0]["value"] == 100 and "iqr" in an[0]["rules"]
    x = [{"label": "A", "year": y, "value": y} for y in range(2010, 2020)]
    y = [{"label": "A", "year": yy, "value": 3 * yy + 7} for yy in range(2010, 2020)]
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "correlation", "data": x, "data_y": y}, headers=h)
    assert abs(r.json()["result"]["pearson_r"] - 1.0) < 1e-9 and r.json()["result"]["strength"] == "strong"
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "risk_score", "indicators": [{"code": "flood", "weight": 1, "values": [{"label": "A", "value": 1}, {"label": "B", "value": 9}]}]}, headers=h)
    res = r.json()["result"]
    assert res["items"][0]["label"] == "B" and res["items"][0]["risk_score"] == 100.0 and res["value_kind"] == "MODELLED"


def test_spatial_aggregate_rolls_up_to_state(client, dataset, demo_geography):
    r = client.post("/api/v1/analytics/run", json={"analysis_type": "spatial_aggregate", "dataset_version_id": dataset["version"]["id"], "variable_code": "cropping_intensity", "level": "state", "year": 2023}, headers=dataset["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["result"]["items"]
    assert len(items) == 1 and items[0]["name"] == "Test State" and items[0]["children"] == 2
    assert abs(items[0]["sum"] - (116 + 144)) < 1e-6


def test_models_registry_and_runs(client, dataset):
    r = client.get("/api/v1/analytics/models", headers=dataset["headers"])
    assert r.status_code == 200 and len(r.json()["items"]) >= 9
    assert all(m["versions"] and m["versions"][0]["limitations"] for m in r.json()["items"] if m["slug"].startswith("analytics-"))
    r = client.get("/api/v1/analytics/runs", headers=dataset["headers"])
    assert r.json()["items"] and r.json()["items"][0]["status"] == "completed"
