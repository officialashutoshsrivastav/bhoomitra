from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.gis.service import layer_statistics
from app.models.gis import AdminUnit, GISLayer
from app.models.intelligence import AnalysisModel, Assumption, ModelVersion, NodeType, Scenario, ScenarioStatus, SimulationResult, SimulationRun
from app.services import evidence_service

MODEL_SLUG = "land-use-reallocation-v1"
LAND_CLASSES = ["cropland", "forest", "grassland", "built_up", "water", "wasteland"]

# Coefficients are explicit, documented ASSUMPTIONS with uncertainty ranges.
# Units: per km² of land class per year unless noted. Values are illustrative
# planning-level magnitudes and must be calibrated with official statistics.
DEFAULT_COEFFICIENTS: Dict[str, Dict[str, Any]] = {
    "carbon_stock_tC_per_km2": {"cropland": [4000, 6000], "forest": [12000, 20000], "grassland": [5000, 8000], "built_up": [500, 1500], "water": [0, 100], "wasteland": [500, 1500], "basis": "Order-of-magnitude biomass+soil carbon densities for Indian ecoregions (literature ranges)"},
    "runoff_coefficient": {"cropland": [0.30, 0.45], "forest": [0.10, 0.25], "grassland": [0.20, 0.35], "built_up": [0.70, 0.90], "water": [1.0, 1.0], "wasteland": [0.45, 0.65], "basis": "Rational-method runoff coefficients by cover type"},
    "recharge_fraction": {"cropland": [0.12, 0.22], "forest": [0.20, 0.35], "grassland": [0.15, 0.25], "built_up": [0.02, 0.08], "water": [0.30, 0.50], "wasteland": [0.08, 0.15], "basis": "Fraction of rainfall recharging groundwater by cover"},
    "crop_output_tonnes_per_km2": {"cropland": [150, 350], "basis": "Foodgrain-equivalent yield 1.5–3.5 t/ha"},
    "agri_jobs_per_km2": {"cropland": [60, 120], "forest": [5, 15], "grassland": [10, 25], "built_up": [0, 0], "water": [5, 20], "wasteland": [0, 5], "basis": "Agricultural/forest livelihood density"},
    "nonfarm_jobs_per_km2_builtup": {"built_up": [800, 2500], "basis": "Non-farm employment density in built-up land"},
    "land_value_index_per_km2": {"cropland": [1.0, 2.0], "forest": [0.3, 0.8], "grassland": [0.5, 1.0], "built_up": [8.0, 20.0], "water": [0.2, 0.5], "wasteland": [0.2, 0.6], "basis": "Relative land value multipliers (cropland = 1)"},
    "biodiversity_weight": {"cropland": [0.2, 0.35], "forest": [0.8, 1.0], "grassland": [0.5, 0.7], "built_up": [0.02, 0.08], "water": [0.5, 0.7], "wasteland": [0.1, 0.25], "basis": "Habitat quality weights (0–1)"},
    "yield_growth_pct_per_year": {"value": [0.5, 1.5], "basis": "Autonomous productivity growth"},
    "population_growth_pct_per_year": {"value": [0.8, 1.4], "basis": "Demographic projection range"},
    "rainfall_mm": {"value": [700, 1300], "basis": "Annual rainfall band; scenario-specific"},
    "food_need_tonnes_per_1000_people": {"value": [180, 220], "basis": "Foodgrain requirement ~0.18–0.22 t/person/yr"},
}

INDICATORS = [
    ("cropland_area_km2", "Cropland area", "km²", "land"),
    ("forest_area_km2", "Forest area", "km²", "land"),
    ("built_up_area_km2", "Built-up area", "km²", "land"),
    ("carbon_stock_MtC", "Carbon stock", "MtC", "environment"),
    ("biodiversity_index", "Biodiversity habitat index", "0-100", "environment"),
    ("crop_output_kt", "Crop output", "kilotonnes", "agriculture"),
    ("food_self_sufficiency_pct", "Food self-sufficiency", "%", "agriculture"),
    ("runoff_volume_Mm3", "Surface runoff", "Mm³", "water"),
    ("groundwater_recharge_Mm3", "Groundwater recharge", "Mm³", "water"),
    ("flood_risk_index", "Flood risk index", "0-100", "water"),
    ("agri_employment_k", "Agricultural livelihoods", "thousand", "social"),
    ("nonfarm_employment_k", "Non-farm employment", "thousand", "social"),
    ("land_value_index", "Aggregate land value index", "index", "economy"),
    ("population_k", "Population", "thousand", "social"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Model registration
# ---------------------------------------------------------------------------
def ensure_model(db: Session) -> ModelVersion:
    model = db.scalar(select(AnalysisModel).where(AnalysisModel.slug == MODEL_SLUG))
    if not model:
        model = AnalysisModel(name="Land-use reallocation impact model", slug=MODEL_SLUG, model_type="simulation", objective="Project multi-domain outcomes (land, agriculture, water, environment, economy, social) of land-use interventions over a planning horizon", description="Transparent coefficient-based accounting model with Monte Carlo propagation of coefficient uncertainty. Not a calibrated econometric or process model.")
        db.add(model)
        db.flush()
        mv = ModelVersion(model_id=model.id, version="1.0.0", algorithm="annual land-class accounting × coefficient sampling (uniform within stated ranges)", features=["baseline land classes (km²)", "population", "rainfall", "interventions"], parameters={"coefficients": DEFAULT_COEFFICIENTS, "indicators": [i[0] for i in INDICATORS]}, limitations="Coefficients are illustrative ranges, not district-calibrated values; no market feedbacks, migration, price effects or climate dynamics; linear ramping of interventions; outputs are decision-support projections, not forecasts.", is_default=True, evaluation={"validation": "unit tests on conservation of land area and monotonic responses"})
        db.add(mv)
        db.flush()
        db.commit()
        return mv
    return db.scalar(select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.is_default.is_(True))) or model.versions[-1]


# ---------------------------------------------------------------------------
# Baseline helpers
# ---------------------------------------------------------------------------
_LAYER_CLASS_MAP = {"cropland": "cropland", "crop": "cropland", "agriculture": "cropland", "forest": "forest", "dense_vegetation": "forest", "grassland": "grassland", "sparse_vegetation": "grassland", "built_up": "built_up", "urban": "built_up", "water": "water", "waterbody": "water", "wasteland": "wasteland", "barren": "wasteland"}


def baseline_from_layer(db: Session, layer_id: uuid.UUID, admin_unit_id: Optional[uuid.UUID]) -> Dict[str, Any]:
    layer = db.get(GISLayer, layer_id)
    if not layer:
        raise NotFoundError("Layer not found")
    stats = layer_statistics(db, layer, admin_unit_id)
    classes = {c: 0.0 for c in LAND_CLASSES}
    for c in stats["classes"]:
        key = _LAYER_CLASS_MAP.get((c["class"] or "").lower())
        if key:
            classes[key] += c["area_km2"]
    return {"land_km2": {k: round(v, 3) for k, v in classes.items()}, "source": {"type": "gis_layer", "layer_id": str(layer_id), "admin_unit_id": str(admin_unit_id) if admin_unit_id else None, "is_demo": layer.is_demo}, "value_kind": "OBSERVED" if not layer.is_demo else "OBSERVED (Demo / Synthetic Data)"}


def validate_baseline(baseline: Dict[str, Any]) -> Dict[str, Any]:
    land = baseline.get("land_km2") or {}
    if not land or sum(float(land.get(c, 0) or 0) for c in LAND_CLASSES) <= 0:
        raise ValidationFailed("baseline.land_km2 must contain positive areas for land classes " + ", ".join(LAND_CLASSES))
    out = {"land_km2": {c: float(land.get(c, 0) or 0) for c in LAND_CLASSES}, "population_k": float(baseline.get("population_k") or 0), "rainfall_mm": float(baseline.get("rainfall_mm") or 0) or None, "base_year": int(baseline.get("base_year") or 2024), "source": baseline.get("source") or {"type": "manual"}, "value_kind": baseline.get("value_kind") or ("ASSUMPTION" if (baseline.get("source") or {}).get("type", "manual") == "manual" else "OBSERVED")}
    return out


def validate_interventions(interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, iv in enumerate(interventions or []):
        t = iv.get("type")
        if t == "reallocate":
            if iv.get("from_class") not in LAND_CLASSES or iv.get("to_class") not in LAND_CLASSES:
                raise ValidationFailed(f"intervention {i}: from_class/to_class must be in {LAND_CLASSES}")
            if float(iv.get("area_km2", 0)) <= 0:
                raise ValidationFailed(f"intervention {i}: area_km2 must be positive")
        elif t == "yield_improvement":
            if not (0 < float(iv.get("pct", 0)) <= 200):
                raise ValidationFailed(f"intervention {i}: pct must be in (0, 200]")
        elif t == "irrigation_expansion":
            if float(iv.get("area_km2", 0)) <= 0:
                raise ValidationFailed(f"intervention {i}: area_km2 must be positive")
        elif t == "rainfall_shift":
            if not (-50 <= float(iv.get("pct", 0)) <= 50):
                raise ValidationFailed(f"intervention {i}: pct must be within ±50")
        else:
            raise ValidationFailed(f"intervention {i}: type must be reallocate|yield_improvement|irrigation_expansion|rainfall_shift")
        out.append({**iv, "start_year_offset": int(iv.get("start_year_offset", 1)), "ramp_years": max(1, int(iv.get("ramp_years", 5)))})
    return out


# ---------------------------------------------------------------------------
# Core simulation (vectorised over Monte Carlo draws)
# ---------------------------------------------------------------------------
def _sample(rng: np.random.Generator, rng_pair: List[float], n: int) -> np.ndarray:
    lo, hi = float(rng_pair[0]), float(rng_pair[1])
    return rng.uniform(lo, hi, n) if hi > lo else np.full(n, lo)


def simulate(baseline: Dict[str, Any], interventions: List[Dict[str, Any]], horizon_years: int, iterations: int, seed: int, coefficients: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    coef = coefficients or DEFAULT_COEFFICIENTS
    rng = np.random.default_rng(seed)
    n = iterations
    base_year = baseline["base_year"]
    years = list(range(base_year, base_year + horizon_years + 1))
    land0 = {c: baseline["land_km2"][c] for c in LAND_CLASSES}
    total_area = sum(land0.values())
    pop0 = baseline["population_k"] or 0.0
    rain0 = baseline["rainfall_mm"]

    def s(key: str, sub: str) -> np.ndarray:
        entry = coef[key]
        return _sample(rng, entry[sub] if sub in entry else [0, 0], n)

    carbon = {c: s("carbon_stock_tC_per_km2", c) for c in LAND_CLASSES}
    runoff = {c: s("runoff_coefficient", c) for c in LAND_CLASSES}
    recharge = {c: s("recharge_fraction", c) for c in LAND_CLASSES}
    crop_out = s("crop_output_tonnes_per_km2", "cropland")
    agri_jobs = {c: s("agri_jobs_per_km2", c) for c in LAND_CLASSES}
    nonfarm = s("nonfarm_jobs_per_km2_builtup", "built_up")
    land_val = {c: s("land_value_index_per_km2", c) for c in LAND_CLASSES}
    biodiv = {c: s("biodiversity_weight", c) for c in LAND_CLASSES}
    yield_g = s("yield_growth_pct_per_year", "value") / 100
    pop_g = s("population_growth_pct_per_year", "value") / 100
    rainfall = np.full(n, rain0) if rain0 else s("rainfall_mm", "value")
    food_need = s("food_need_tonnes_per_1000_people", "value")

    series: Dict[str, List[Dict[str, Any]]] = {k[0]: [] for k in INDICATORS}
    scenario_flags: Dict[str, str] = {}
    land = {c: np.full(n, land0[c]) for c in LAND_CLASSES}
    yield_mult = np.ones(n)
    irrigation_bonus = np.zeros(n)
    rain_mult = np.ones(n)
    for yi, year in enumerate(years):
        # apply interventions with linear ramps
        if yi > 0:
            for iv in interventions:
                start, ramp = iv["start_year_offset"], iv["ramp_years"]
                if yi < start:
                    continue
                step = 1.0 / ramp if yi < start + ramp else 0.0
                if iv["type"] == "reallocate" and step > 0:
                    amt = min(float(iv["area_km2"]) * step, 1e9)
                    move = np.minimum(land[iv["from_class"]], amt)
                    land[iv["from_class"]] = land[iv["from_class"]] - move
                    land[iv["to_class"]] = land[iv["to_class"]] + move
                    scenario_flags[f"{iv['from_class']}->{iv['to_class']}"] = "SCENARIO"
                elif iv["type"] == "yield_improvement" and step > 0:
                    yield_mult = yield_mult * (1 + float(iv["pct"]) / 100 * step)
                elif iv["type"] == "irrigation_expansion" and step > 0:
                    irrigation_bonus = irrigation_bonus + float(iv["area_km2"]) * step * 0.4  # irrigated land ≈ +40% output on that area
                elif iv["type"] == "rainfall_shift" and step > 0:
                    rain_mult = rain_mult * (1 + float(iv["pct"]) / 100 * step)
        yield_mult = yield_mult * (1 + yield_g) if yi > 0 else yield_mult
        pop = pop0 * (1 + pop_g) ** yi
        rain = rainfall * rain_mult
        crop_output = (land["cropland"] * crop_out + irrigation_bonus * crop_out) * yield_mult  # tonnes
        food_needed = pop * food_need  # tonnes (pop in thousands)
        carbon_stock = sum(land[c] * carbon[c] for c in LAND_CLASSES) / 1e6  # MtC
        runoff_vol = sum(land[c] * runoff[c] for c in LAND_CLASSES) * rain / 1e3  # km² × mm → 1e-3 Mm³ … (1 km² × 1 mm = 1000 m³ = 0.001 Mm³)
        recharge_vol = sum(land[c] * recharge[c] for c in LAND_CLASSES) * rain / 1e3
        weighted_runoff = sum(land[c] * runoff[c] for c in LAND_CLASSES) / total_area
        flood_idx = np.clip(100 * (weighted_runoff - 0.1) / 0.8 * (rain / 1000.0), 0, 100)
        biodiv_idx = 100 * sum(land[c] * biodiv[c] for c in LAND_CLASSES) / total_area
        agri_emp = sum(land[c] * agri_jobs[c] for c in LAND_CLASSES) / 1e3
        nonfarm_emp = land["built_up"] * nonfarm / 1e3
        land_value = sum(land[c] * land_val[c] for c in LAND_CLASSES) / total_area
        self_suff = np.where(food_needed > 0, np.clip(100 * crop_output / np.maximum(food_needed, 1e-9), 0, 400), np.nan)
        vals = {
            "cropland_area_km2": land["cropland"], "forest_area_km2": land["forest"], "built_up_area_km2": land["built_up"],
            "carbon_stock_MtC": carbon_stock, "biodiversity_index": biodiv_idx, "crop_output_kt": crop_output / 1e3,
            "food_self_sufficiency_pct": self_suff, "runoff_volume_Mm3": runoff_vol, "groundwater_recharge_Mm3": recharge_vol,
            "flood_risk_index": flood_idx, "agri_employment_k": agri_emp, "nonfarm_employment_k": nonfarm_emp,
            "land_value_index": land_value, "population_k": np.full(n, pop) if np.isscalar(pop) else pop,
        }
        for code, arr in vals.items():
            arr = np.asarray(arr, dtype=float)
            if np.all(np.isnan(arr)):
                series[code].append({"year": year, "value": None, "low": None, "high": None})
                continue
            med, p10, p90 = np.nanpercentile(arr, [50, 10, 90])
            series[code].append({"year": year, "value": round(float(med), 4), "low": round(float(p10), 4), "high": round(float(p90), 4)})
    # summary: change from base year to horizon end
    summary = {}
    for code, label, unit, domain in INDICATORS:
        first, last = series[code][0], series[code][-1]
        if first["value"] is None or last["value"] is None:
            continue
        delta = last["value"] - first["value"]
        summary[code] = {"label": label, "unit": unit, "domain": domain, "base": first["value"], "end": last["value"], "change": round(delta, 4), "change_pct": round(100 * delta / first["value"], 2) if first["value"] else None, "end_low": last["low"], "end_high": last["high"]}
    land_end = {c: round(float(np.median(land[c])), 3) for c in LAND_CLASSES}
    area_conserved = abs(sum(land_end.values()) - total_area) < 1e-6 * max(1.0, total_area)
    return {"years": years, "series": series, "summary": summary, "land_end_km2": land_end, "total_area_km2": round(total_area, 3), "area_conserved": bool(area_conserved), "iterations": n, "seed": seed, "scenario_flags": scenario_flags}


def assess_risks(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    risks = []
    def chg(code):
        return summary.get(code, {}).get("change_pct")
    if (chg("forest_area_km2") or 0) < -5:
        risks.append({"domain": "environment", "severity": "high", "statement": f"Forest area declines {chg('forest_area_km2')}%, reducing carbon stock and habitat.", "value_kind": "MODELLED"})
    if (chg("food_self_sufficiency_pct") or 0) < -5:
        risks.append({"domain": "agriculture", "severity": "high", "statement": f"Food self-sufficiency falls {chg('food_self_sufficiency_pct')}% relative to baseline.", "value_kind": "MODELLED"})
    if (chg("flood_risk_index") or 0) > 5:
        risks.append({"domain": "water", "severity": "medium", "statement": f"Flood risk index rises {chg('flood_risk_index')}% due to higher runoff.", "value_kind": "MODELLED"})
    if (chg("groundwater_recharge_Mm3") or 0) < -5:
        risks.append({"domain": "water", "severity": "medium", "statement": f"Groundwater recharge declines {chg('groundwater_recharge_Mm3')}%.", "value_kind": "MODELLED"})
    if (chg("agri_employment_k") or 0) < -5:
        risks.append({"domain": "social", "severity": "medium", "statement": f"Agricultural livelihoods decline {chg('agri_employment_k')}%; transition support may be needed.", "value_kind": "MODELLED"})
    if (chg("biodiversity_index") or 0) < -5:
        risks.append({"domain": "environment", "severity": "medium", "statement": f"Habitat index declines {chg('biodiversity_index')}%.", "value_kind": "MODELLED"})
    if not risks:
        risks.append({"domain": "overall", "severity": "low", "statement": "No indicator crosses the ±5% risk thresholds within the modelled ranges.", "value_kind": "MODELLED"})
    return risks


# ---------------------------------------------------------------------------
# Scenario lifecycle
# ---------------------------------------------------------------------------
def get_scenario(db: Session, sid: uuid.UUID) -> Scenario:
    sc = db.get(Scenario, sid)
    if not sc:
        raise NotFoundError("Scenario not found")
    return sc


def create_scenario(db: Session, *, name: str, description: Optional[str], baseline: Dict[str, Any], interventions: List[Dict[str, Any]], constraints: Optional[Dict[str, Any]], horizon_years: int, admin_unit_id: Optional[uuid.UUID], baseline_layer_id: Optional[uuid.UUID], baseline_dataset_version_id: Optional[uuid.UUID], workspace_id: Optional[uuid.UUID], parent_scenario_id: Optional[uuid.UUID], user_id: uuid.UUID, extra_assumptions: Optional[List[Dict[str, Any]]] = None, is_demo: bool = False) -> Scenario:
    if baseline_layer_id:
        derived = baseline_from_layer(db, baseline_layer_id, admin_unit_id)
        baseline = {**baseline, "land_km2": derived["land_km2"], "source": derived["source"], "value_kind": "OBSERVED"}
    baseline = validate_baseline(baseline)
    interventions = validate_interventions(interventions)
    if admin_unit_id and not db.get(AdminUnit, admin_unit_id):
        raise NotFoundError("Administrative unit not found")
    sc = Scenario(name=name, description=description, baseline=baseline, interventions=interventions, constraints=constraints, horizon_years=horizon_years, admin_unit_id=admin_unit_id, baseline_dataset_version_id=baseline_dataset_version_id, workspace_id=workspace_id, parent_scenario_id=parent_scenario_id, created_by=user_id, is_demo=is_demo or bool((baseline.get("source") or {}).get("is_demo")))
    db.add(sc)
    db.flush()
    # explicit assumptions rows
    db.add(Assumption(scenario_id=sc.id, code="baseline_source", statement=f"Baseline land classes come from {baseline['source'].get('type')} ({baseline['value_kind']})", basis=str(baseline["source"])))
    for key, entry in DEFAULT_COEFFICIENTS.items():
        for sub, rng_pair in entry.items():
            if sub == "basis" or not isinstance(rng_pair, list):
                continue
            db.add(Assumption(scenario_id=sc.id, code=f"{key}.{sub}", statement=f"{key.replace('_', ' ')} for {sub}: {rng_pair[0]}–{rng_pair[1]}", value=float(np.mean(rng_pair)), low=float(rng_pair[0]), high=float(rng_pair[1]), unit=key.split("_per_")[-1] if "_per_" in key else None, basis=entry.get("basis")))
    for a in extra_assumptions or []:
        db.add(Assumption(scenario_id=sc.id, code=str(a.get("code", "custom"))[:80], statement=str(a.get("statement", ""))[:2000], value=a.get("value"), low=a.get("low"), high=a.get("high"), unit=a.get("unit"), basis=a.get("basis")))
    db.commit()
    db.refresh(sc)
    return sc


def run_scenario(db: Session, sc: Scenario, *, iterations: int, seed: Optional[int], user_id: Optional[uuid.UUID]) -> SimulationRun:
    if sc.status == ScenarioStatus.ARCHIVED:
        raise ConflictError("Archived scenarios cannot be run")
    mv = ensure_model(db)
    seed = seed if seed is not None else int(time.time()) % 100000
    run = SimulationRun(scenario_id=sc.id, model_version_id=mv.id, seed=seed, iterations=iterations, status="running", created_by=user_id, started_at=_now())
    db.add(run)
    db.flush()
    try:
        out = simulate(sc.baseline, sc.interventions or [], sc.horizon_years, iterations, seed, (mv.parameters or {}).get("coefficients"))
        base_kind = "OBSERVED" if sc.baseline.get("value_kind", "").startswith("OBSERVED") else "ASSUMPTION"
        rows = []
        for code, label, unit, domain in INDICATORS:
            for pt in out["series"][code]:
                if pt["value"] is None:
                    continue
                is_base = pt["year"] == out["years"][0]
                kind = base_kind if is_base and code.endswith("_km2") else ("SCENARIO" if code.endswith("_km2") else "MODELLED")
                rows.append(SimulationResult(run_id=run.id, indicator_code=code, indicator_name=label, domain=domain, unit=unit, year=pt["year"], value=pt["value"], low=pt["low"], high=pt["high"], value_kind=kind))
        db.add_all(rows)
        risks = assess_risks(out["summary"])
        run.summary = {"summary": out["summary"], "land_end_km2": out["land_end_km2"], "total_area_km2": out["total_area_km2"], "area_conserved": out["area_conserved"], "years": out["years"], "value_kinds": {"baseline": base_kind, "land_paths": "SCENARIO", "indicators": "MODELLED", "bands": "UNCERTAINTY (p10–p90 over coefficient draws)"}}
        run.risks = risks
        run.status = "completed"
        run.completed_at = _now()
        if sc.status == ScenarioStatus.DRAFT:
            sc.status = ScenarioStatus.SIMULATED
        # Recommendation + evidence trace
        top = sorted(out["summary"].items(), key=lambda kv: -abs(kv[1]["change_pct"] or 0))[:3]
        statement = "; ".join(f"{v['label']} {v['change_pct']:+}% by {out['years'][-1]}" for _, v in top if v["change_pct"] is not None) or "No material change"
        rec = evidence_service.create_recommendation(db, kind="simulation", title=f"Scenario '{sc.name}' projection", statement=f"MODELLED projection: {statement}. Bands are p10–p90 UNCERTAINTY across coefficient assumptions.", created_by=user_id, confidence=0.45 if base_kind == "OBSERVED" else 0.3, confidence_basis="illustrative coefficient ranges; uncalibrated model; baseline " + base_kind, limitations=mv.limitations, assumptions=[{"code": a.code, "statement": a.statement, "low": a.low, "high": a.high, "basis": a.basis} for a in sc.assumptions[:60]], model_version_id=mv.id, scenario_id=sc.id, simulation_run_id=run.id, is_demo=sc.is_demo)
        run.recommendation_id = rec.id
        evidence_service.add_evidence(db, rec, source_type=NodeType.SCENARIO, source_id=sc.id, label=f"Scenario definition: {len(sc.interventions or [])} intervention(s)", excerpt=str(sc.interventions)[:600], value_kind="SCENARIO")
        evidence_service.add_evidence(db, rec, source_type=NodeType.SIMULATION_RUN, source_id=run.id, label=f"Simulation run (seed {seed}, {iterations} draws)", excerpt=str(out["summary"])[:600], value_kind="MODELLED")
        if sc.baseline_dataset_version_id:
            evidence_service.add_evidence(db, rec, source_type=NodeType.DATASET_VERSION, source_id=sc.baseline_dataset_version_id, label="Baseline dataset version", value_kind="OBSERVED")
        src = sc.baseline.get("source") or {}
        if src.get("type") == "gis_layer" and src.get("layer_id"):
            evidence_service.add_evidence(db, rec, source_type=NodeType.GIS_LAYER, source_id=uuid.UUID(src["layer_id"]), label="Baseline land-cover layer", value_kind="OBSERVED")
        for a in sc.assumptions[:8]:
            evidence_service.add_evidence(db, rec, source_type=NodeType.ASSUMPTION, source_id=a.id, label=a.statement[:200], value_kind="ASSUMPTION")
        db.commit()
        db.refresh(run)
        return run
    except Exception as exc:
        db.rollback()
        run = db.get(SimulationRun, run.id)
        if run:
            run.status = "failed"
            run.error = str(exc)[:1000]
            run.completed_at = _now()
            db.commit()
        raise


def run_dict(db: Session, run: SimulationRun, include_series: bool = True) -> Dict[str, Any]:
    out = {"id": str(run.id), "scenario_id": str(run.scenario_id), "status": run.status, "seed": run.seed, "iterations": run.iterations, "summary": run.summary, "risks": run.risks, "error": run.error, "recommendation_id": str(run.recommendation_id) if run.recommendation_id else None, "model_version_id": str(run.model_version_id) if run.model_version_id else None, "started_at": run.started_at.isoformat() if run.started_at else None, "completed_at": run.completed_at.isoformat() if run.completed_at else None, "duration_ms": int((run.completed_at - run.started_at).total_seconds() * 1000) if run.completed_at and run.started_at else None, "disclaimer": "Decision-support projection. MODELLED values with UNCERTAINTY bands; not a forecast or official statistic."}
    if include_series:
        series: Dict[str, Dict[str, Any]] = {}
        for r in db.scalars(select(SimulationResult).where(SimulationResult.run_id == run.id).order_by(SimulationResult.indicator_code, SimulationResult.year)).all():
            s = series.setdefault(r.indicator_code, {"label": r.indicator_name, "unit": r.unit, "domain": r.domain, "points": []})
            s["points"].append({"year": r.year, "value": r.value, "low": r.low, "high": r.high, "value_kind": r.value_kind})
        out["series"] = series
    return out


def compare_runs(db: Session, run_ids: List[uuid.UUID]) -> Dict[str, Any]:
    runs = [db.get(SimulationRun, r) for r in run_ids]
    if any(r is None for r in runs) or len(runs) < 2:
        raise ValidationFailed("Provide at least two valid run ids")
    scenarios = {str(r.id): db.get(Scenario, r.scenario_id) for r in runs}
    table = []
    for code, label, unit, domain in INDICATORS:
        row = {"indicator": code, "label": label, "unit": unit, "domain": domain, "runs": {}}
        for r in runs:
            s = (r.summary or {}).get("summary", {}).get(code)
            if s:
                row["runs"][str(r.id)] = {"scenario": scenarios[str(r.id)].name, "base": s["base"], "end": s["end"], "change_pct": s["change_pct"], "end_low": s["end_low"], "end_high": s["end_high"]}
        if row["runs"]:
            ends = [v["end"] for v in row["runs"].values()]
            row["best_run_id"] = max(row["runs"], key=lambda k: row["runs"][k]["end"]) if code not in ("flood_risk_index", "runoff_volume_Mm3", "built_up_area_km2") else min(row["runs"], key=lambda k: row["runs"][k]["end"])
            row["spread"] = round(max(ends) - min(ends), 4)
            table.append(row)
    return {"runs": [{"id": str(r.id), "scenario": scenarios[str(r.id)].name, "scenario_id": str(r.scenario_id), "status": r.status, "iterations": r.iterations, "is_demo": scenarios[str(r.id)].is_demo} for r in runs], "comparison": table, "value_kind": "MODELLED", "note": "'best' uses higher-is-better except for flood risk, runoff and built-up area; policy judgement must weigh domains explicitly."}


def transition(db: Session, sc: Scenario, new_status: ScenarioStatus, user_id: uuid.UUID, note: Optional[str] = None) -> Scenario:
    allowed = {ScenarioStatus.DRAFT: [ScenarioStatus.SIMULATED, ScenarioStatus.ARCHIVED], ScenarioStatus.SIMULATED: [ScenarioStatus.UNDER_REVIEW, ScenarioStatus.DRAFT, ScenarioStatus.ARCHIVED], ScenarioStatus.UNDER_REVIEW: [ScenarioStatus.APPROVED, ScenarioStatus.REJECTED, ScenarioStatus.SIMULATED], ScenarioStatus.APPROVED: [ScenarioStatus.ARCHIVED], ScenarioStatus.REJECTED: [ScenarioStatus.DRAFT, ScenarioStatus.ARCHIVED], ScenarioStatus.ARCHIVED: []}
    if new_status not in allowed.get(sc.status, []):
        raise ConflictError(f"Cannot move scenario from {sc.status.value} to {new_status.value}")
    sc.status = new_status
    if new_status in (ScenarioStatus.APPROVED, ScenarioStatus.REJECTED):
        sc.approved_by = user_id
        sc.parameters = {**(sc.parameters or {}), "review_note": note, "reviewed_at": _now().isoformat()}
    db.commit()
    return sc


def scenario_dict(sc: Scenario, db: Session) -> Dict[str, Any]:
    unit = db.get(AdminUnit, sc.admin_unit_id) if sc.admin_unit_id else None
    return {"id": str(sc.id), "name": sc.name, "description": sc.description, "status": sc.status.value, "baseline": sc.baseline, "interventions": sc.interventions, "constraints": sc.constraints, "horizon_years": sc.horizon_years, "admin_unit": {"id": str(unit.id), "name": unit.name, "level": unit.level.value} if unit else None, "workspace_id": str(sc.workspace_id) if sc.workspace_id else None, "parent_scenario_id": str(sc.parent_scenario_id) if sc.parent_scenario_id else None, "created_by": str(sc.created_by), "reviewed_by": str(sc.approved_by) if sc.approved_by else None, "review_note": (sc.parameters or {}).get("review_note"), "is_demo": sc.is_demo, "created_at": sc.created_at.isoformat(), "assumptions": [{"id": str(a.id), "code": a.code, "statement": a.statement, "value": a.value, "low": a.low, "high": a.high, "unit": a.unit, "basis": a.basis} for a in sc.assumptions], "runs": [{"id": str(r.id), "status": r.status, "iterations": r.iterations, "seed": r.seed, "created_at": r.created_at.isoformat(), "recommendation_id": str(r.recommendation_id) if r.recommendation_id else None} for r in sc.runs]}
