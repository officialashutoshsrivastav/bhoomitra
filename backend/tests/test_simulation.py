import pytest

BASELINE = {"land_km2": {"cropland": 500, "forest": 200, "grassland": 100, "built_up": 80, "water": 40, "wasteland": 120}, "population_k": 900, "rainfall_mm": 900, "base_year": 2024}


@pytest.fixture(scope="module")
def scenario_runs(client, policy_maker):
    ph, _ = policy_maker
    r = client.post("/api/v1/simulations/scenarios", json={"name": "Test afforestation", "baseline": BASELINE, "interventions": [{"type": "reallocate", "from_class": "wasteland", "to_class": "forest", "area_km2": 100, "start_year_offset": 1, "ramp_years": 5}], "horizon_years": 10}, headers=ph)
    assert r.status_code == 201, r.text
    sc = r.json()
    run = client.post(f"/api/v1/simulations/scenarios/{sc['id']}/run", json={"iterations": 200, "seed": 3}, headers=ph).json()
    r2 = client.post("/api/v1/simulations/scenarios", json={"name": "Test urbanisation", "baseline": BASELINE, "interventions": [{"type": "reallocate", "from_class": "cropland", "to_class": "built_up", "area_km2": 150, "start_year_offset": 1, "ramp_years": 5}], "horizon_years": 10}, headers=ph).json()
    run2 = client.post(f"/api/v1/simulations/scenarios/{r2['id']}/run", json={"iterations": 200, "seed": 3}, headers=ph).json()
    return {"headers": ph, "sc": sc, "run": run, "sc2": r2, "run2": run2}


def test_scenario_has_explicit_assumptions(scenario_runs):
    sc = scenario_runs["sc"]
    assert sc["status"] == "draft" and len(sc["assumptions"]) > 30
    codes = {a["code"] for a in sc["assumptions"]}
    assert "baseline_source" in codes and "carbon_stock_tC_per_km2.forest" in codes
    assert all(a["low"] <= a["high"] for a in sc["assumptions"] if a["low"] is not None)


def test_run_conserves_area_and_applies_intervention(scenario_runs):
    run = scenario_runs["run"]
    assert run["status"] == "completed"
    s = run["summary"]
    assert s["area_conserved"] is True and abs(sum(s["land_end_km2"].values()) - 1040) < 1e-6
    assert abs(s["land_end_km2"]["forest"] - 300) < 1e-6 and abs(s["land_end_km2"]["wasteland"] - 20) < 1e-6
    forest = s["summary"]["forest_area_km2"]
    assert forest["base"] == 200 and forest["end"] == 300 and forest["change_pct"] == 50.0
    assert s["value_kinds"]["bands"].startswith("UNCERTAINTY")


def test_results_carry_value_kinds_and_bands(scenario_runs):
    series = scenario_runs["run"]["series"]
    carbon = series["carbon_stock_MtC"]["points"]
    assert len(carbon) == 11 and carbon[0]["year"] == 2024 and carbon[-1]["year"] == 2034
    assert all(p["low"] <= p["value"] <= p["high"] for p in carbon)
    assert carbon[-1]["value"] > carbon[0]["value"], "afforestation should raise carbon stock"
    kinds = {p["value_kind"] for s in series.values() for p in s["points"]}
    assert {"MODELLED", "SCENARIO", "ASSUMPTION"} <= kinds
    assert series["forest_area_km2"]["points"][0]["value_kind"] == "ASSUMPTION", "manual baseline is an assumption"


def test_risks_flag_urbanisation(scenario_runs):
    run2 = scenario_runs["run2"]
    domains = {r["domain"] for r in run2["risks"]}
    assert "agriculture" in domains or "social" in domains
    assert all(r["value_kind"] == "MODELLED" for r in run2["risks"])
    assert run2["summary"]["summary"]["flood_risk_index"]["change"] > 0


def test_compare_runs(client, scenario_runs):
    h = scenario_runs["headers"]
    r = client.get("/api/v1/simulations/compare", params={"run_ids": f"{scenario_runs['run']['id']},{scenario_runs['run2']['id']}"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    forest = next(row for row in body["comparison"] if row["indicator"] == "forest_area_km2")
    assert forest["best_run_id"] == scenario_runs["run"]["id"] and forest["spread"] == 100.0
    assert body["value_kind"] == "MODELLED"


def test_review_lifecycle_and_permissions(client, scenario_runs, researcher):
    h = scenario_runs["headers"]
    sid = scenario_runs["sc"]["id"]
    assert client.get(f"/api/v1/simulations/scenarios/{sid}", headers=h).json()["status"] == "simulated"
    r = client.post(f"/api/v1/simulations/scenarios/{sid}/review", json={"decision": "approve"}, headers=h)
    assert r.status_code == 409, "cannot approve before submission"
    assert client.post(f"/api/v1/simulations/scenarios/{sid}/review", json={"decision": "submit"}, headers=h).json()["status"] == "under_review"
    rh, _ = researcher
    assert client.post(f"/api/v1/simulations/scenarios/{sid}/review", json={"decision": "approve"}, headers=rh).status_code == 403
    out = client.post(f"/api/v1/simulations/scenarios/{sid}/review", json={"decision": "approve", "note": "ok"}, headers=h).json()
    assert out["status"] == "approved" and out["review_note"] == "ok"


def test_evidence_trace_links_assumptions_and_model(client, scenario_runs):
    h = scenario_runs["headers"]
    rec = scenario_runs["run"]["recommendation_id"]
    ex = client.get(f"/api/v1/evidence/{rec}", headers=h).json()
    assert {"SCENARIO", "MODELLED", "ASSUMPTION"} <= set(ex["value_kinds_present"])
    tr = client.get(f"/api/v1/evidence/{rec}/trace", headers=h).json()
    assert {"scenario", "simulation_run", "model_version", "assumption"} <= {n["type"] for n in tr["nodes"]}


def test_validation_errors(client, scenario_runs):
    h = scenario_runs["headers"]
    r = client.post("/api/v1/simulations/scenarios", json={"name": "bad", "baseline": {"land_km2": {}}, "interventions": []}, headers=h)
    assert r.status_code == 422
    r = client.post("/api/v1/simulations/scenarios", json={"name": "bad2", "baseline": BASELINE, "interventions": [{"type": "reallocate", "from_class": "moon", "to_class": "forest", "area_km2": 10}]}, headers=h)
    assert r.status_code == 422


def test_model_card_and_pure_engine():
    from app.simulation.engine import DEFAULT_COEFFICIENTS, simulate, validate_baseline, validate_interventions

    base = validate_baseline(BASELINE)
    out = simulate(base, validate_interventions([]), 5, 100, 1, DEFAULT_COEFFICIENTS)
    assert out["area_conserved"] and out["years"] == list(range(2024, 2030))
    a = simulate(base, [], 5, 100, 11, DEFAULT_COEFFICIENTS)
    b = simulate(base, [], 5, 100, 11, DEFAULT_COEFFICIENTS)
    assert a["summary"] == b["summary"], "same seed → deterministic"
