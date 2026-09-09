from __future__ import annotations

import math
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.models.datasets import Dataset, DatasetVersion, Observation
from app.models.gis import AdminUnit
from app.models.intelligence import AnalysisModel, AnalyticsRun, ModelVersion, NodeType
from app.models.knowledge import PolicyIndicator
from app.services import evidence_service

ANALYSIS_TYPES = ["descriptive", "trend", "compare", "correlation", "anomaly", "forecast", "risk_score", "timeseries", "spatial_aggregate"]


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
BUILTIN_MODELS = {
    "descriptive": ("Descriptive statistics", "statistics", "Summarise a variable's distribution", "numpy descriptive statistics", {}, "Assumes numeric, comparable observations; ignores measurement error."),
    "trend": ("Linear trend", "statistics", "Estimate direction and rate of change over time", "ordinary least squares on year index", {"min_points": 3}, "Linear fit only; sensitive to outliers and short series."),
    "compare": ("Geographic comparison", "statistics", "Compare a variable across geographies", "grouped aggregation", {}, "Comparisons ignore differences in data collection across units."),
    "correlation": ("Correlation", "statistics", "Measure association between two variables", "Pearson and Spearman correlation", {"min_points": 4}, "Correlation is not causation; requires aligned periods/geographies."),
    "anomaly": ("Anomaly detection", "statistics", "Flag unusual observations", "z-score (|z|>=2.5) and IQR (1.5×) rules", {"z_threshold": 2.5, "iqr_k": 1.5}, "Rule-based; does not model seasonality; small samples inflate false positives."),
    "forecast": ("Forecast", "forecasting", "Project a series forward with uncertainty", "Holt linear exponential smoothing with residual-based intervals", {"alpha": 0.6, "beta": 0.3}, "Assumes trend persistence; no exogenous drivers; intervals widen with horizon."),
    "risk_score": ("Composite risk score", "scoring", "Combine normalised indicators into a 0-100 risk index", "min-max normalisation + weighted sum", {}, "Weights are user assumptions; scores are relative within the input set only."),
    "timeseries": ("Time-series profile", "statistics", "Year-on-year change, moving average, CAGR", "differencing + rolling mean", {"window": 3}, "Requires regular annual periods; gaps are not interpolated."),
    "spatial_aggregate": ("Spatial aggregate", "spatial", "Roll observations up to an administrative level", "SQL group-by admin hierarchy", {}, "Depends on observation→admin-unit linkage quality."),
}


def ensure_models(db: Session) -> Dict[str, ModelVersion]:
    out: Dict[str, ModelVersion] = {}
    for slug, (name, mtype, objective, algo, params, limits) in BUILTIN_MODELS.items():
        model = db.scalar(select(AnalysisModel).where(AnalysisModel.slug == f"analytics-{slug}"))
        if not model:
            model = AnalysisModel(name=name, slug=f"analytics-{slug}", model_type=mtype, objective=objective, description=f"Built-in analytics model: {name}")
            db.add(model)
            db.flush()
            mv = ModelVersion(model_id=model.id, version="1.0.0", algorithm=algo, features=["value", "period", "admin_unit"], parameters=params, limitations=limits, is_default=True, evaluation={"note": "deterministic statistical procedure; validated by unit tests"})
            db.add(mv)
            db.flush()
        else:
            mv = db.scalar(select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.is_default.is_(True)))
        out[slug] = mv
    db.commit()
    return out


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
def load_series(db: Session, *, dataset_version_id: Optional[uuid.UUID], variable_code: Optional[str], admin_unit_id: Optional[uuid.UUID], indicator_code: Optional[str], inline: Optional[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return list of {x(year), value, label, kind} rows plus provenance info."""
    prov: Dict[str, Any] = {}
    if inline:
        rows = []
        for r in inline:
            if "value" not in r:
                continue
            rows.append({"year": r.get("year") or r.get("x"), "value": float(r["value"]), "label": r.get("label") or r.get("geography"), "kind": r.get("value_kind", "OBSERVED"), "is_demo": bool(r.get("is_demo", False))})
        prov["source"] = "inline"
        return rows, prov
    if indicator_code:
        stmt = select(PolicyIndicator).where(PolicyIndicator.code == indicator_code)
        if admin_unit_id:
            stmt = stmt.where(PolicyIndicator.admin_unit_id == admin_unit_id)
        obs = db.scalars(stmt.order_by(PolicyIndicator.period_start)).all()
        prov = {"source": "policy_indicator", "indicator_code": indicator_code, "dataset_version_ids": sorted({str(o.dataset_version_id) for o in obs if o.dataset_version_id})}
        return [{"year": o.period_start.year if o.period_start else None, "value": o.value, "label": o.name, "kind": o.value_kind, "is_demo": o.is_demo, "admin_unit_id": str(o.admin_unit_id) if o.admin_unit_id else None} for o in obs], prov
    if not dataset_version_id:
        raise ValidationFailed("Provide dataset_version_id, indicator_code or inline data")
    version = db.get(DatasetVersion, dataset_version_id)
    if not version:
        raise NotFoundError("Dataset version not found")
    stmt = select(Observation).where(Observation.dataset_version_id == dataset_version_id)
    if variable_code:
        stmt = stmt.where(Observation.variable_code == variable_code)
    if admin_unit_id:
        stmt = stmt.where(Observation.admin_unit_id == admin_unit_id)
    obs = db.scalars(stmt.order_by(Observation.period_start.nullsfirst(), Observation.geography_label).limit(50000)).all()
    if not obs:
        raise ValidationFailed("No observations match the selection")
    prov = {"source": "dataset_version", "dataset_version_id": str(dataset_version_id), "dataset_id": str(version.dataset_id), "variable_code": variable_code, "rows": len(obs)}
    return [{"year": o.period_start.year if o.period_start else None, "value": o.value, "label": o.geography_label, "kind": o.value_kind, "is_demo": o.is_demo, "admin_unit_id": str(o.admin_unit_id) if o.admin_unit_id else None, "unit": o.unit, "variable": o.variable_code} for o in obs], prov


# ---------------------------------------------------------------------------
# Procedures
# ---------------------------------------------------------------------------
def _vals(rows: List[Dict[str, Any]]) -> np.ndarray:
    return np.asarray([r["value"] for r in rows], dtype=float)


def descriptive(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    v = _vals(rows)
    if v.size == 0:
        raise ValidationFailed("No data")
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    return {"n": int(v.size), "mean": round(float(v.mean()), 4), "std": round(float(v.std(ddof=1)), 4) if v.size > 1 else 0.0, "min": round(float(v.min()), 4), "q1": round(float(q1), 4), "median": round(float(med), 4), "q3": round(float(q3), 4), "max": round(float(v.max()), 4), "sum": round(float(v.sum()), 4), "cv": round(float(v.std(ddof=1) / v.mean()), 4) if v.size > 1 and v.mean() else None, "skewness": round(float(((v - v.mean()) ** 3).mean() / (v.std() ** 3)), 4) if v.size > 2 and v.std() else None}


def _annual(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
    by_year: Dict[int, List[float]] = {}
    for r in rows:
        if r.get("year") is None:
            continue
        by_year.setdefault(int(r["year"]), []).append(r["value"])
    years = np.array(sorted(by_year), dtype=float)
    vals = np.array([float(np.mean(by_year[int(y)])) for y in years])
    return years, vals


def trend(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    years, vals = _annual(rows)
    if years.size < 3:
        raise ValidationFailed("Trend needs at least 3 annual points")
    slope, intercept = np.polyfit(years, vals, 1)
    fitted = slope * years + intercept
    ss_res = float(((vals - fitted) ** 2).sum())
    ss_tot = float(((vals - vals.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    n = years.size
    se = math.sqrt(ss_res / (n - 2)) / math.sqrt(float(((years - years.mean()) ** 2).sum())) if n > 2 and ((years - years.mean()) ** 2).sum() else 0.0
    t = slope / se if se else float("inf")
    pct_per_year = 100 * slope / vals.mean() if vals.mean() else None
    return {"slope_per_year": round(float(slope), 6), "intercept": round(float(intercept), 4), "r_squared": round(r2, 4), "t_statistic": round(t, 3) if math.isfinite(t) else None, "direction": "increasing" if slope > 0 else ("decreasing" if slope < 0 else "flat"), "pct_change_per_year": round(pct_per_year, 3) if pct_per_year is not None else None, "years": years.astype(int).tolist(), "observed": [round(float(x), 4) for x in vals], "fitted": [round(float(x), 4) for x in fitted], "significant_95": bool(abs(t) > 2.0) if math.isfinite(t) else None}


def compare(rows: List[Dict[str, Any]], latest_only: bool = True) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r.get("label") or "unknown", []).append(r)
    items = []
    for label, rs in groups.items():
        if latest_only and any(r.get("year") for r in rs):
            latest_year = max(r["year"] for r in rs if r.get("year") is not None)
            rs_latest = [r for r in rs if r.get("year") == latest_year]
            v = float(np.mean([r["value"] for r in rs_latest]))
            items.append({"label": label, "value": round(v, 4), "year": latest_year, "n": len(rs), "admin_unit_id": rs[0].get("admin_unit_id")})
        else:
            items.append({"label": label, "value": round(float(np.mean([r["value"] for r in rs])), 4), "n": len(rs), "admin_unit_id": rs[0].get("admin_unit_id")})
    items.sort(key=lambda x: -x["value"])
    vals = np.array([i["value"] for i in items])
    mean = float(vals.mean()) if vals.size else 0.0
    for i, it in enumerate(items):
        it["rank"] = i + 1
        it["vs_mean_pct"] = round(100 * (it["value"] - mean) / mean, 2) if mean else None
    return {"groups": len(items), "mean": round(mean, 4), "spread_max_min_ratio": round(float(vals.max() / vals.min()), 3) if vals.size and vals.min() else None, "items": items}


def correlation(rows_x: List[Dict[str, Any]], rows_y: List[Dict[str, Any]]) -> Dict[str, Any]:
    def keyed(rows):
        return {(r.get("label"), r.get("year")): r["value"] for r in rows}

    kx, ky = keyed(rows_x), keyed(rows_y)
    common = sorted(set(kx) & set(ky), key=lambda k: (str(k[0]), k[1] or 0))
    if len(common) < 4:
        raise ValidationFailed("Correlation needs at least 4 aligned (geography, period) pairs")
    x = np.array([kx[k] for k in common])
    y = np.array([ky[k] for k in common])
    pearson = float(np.corrcoef(x, y)[0, 1]) if x.std() and y.std() else 0.0
    rx, ry = x.argsort().argsort(), y.argsort().argsort()
    spearman = float(np.corrcoef(rx, ry)[0, 1]) if rx.std() and ry.std() else 0.0
    n = len(common)
    t = pearson * math.sqrt((n - 2) / max(1e-9, 1 - pearson**2)) if abs(pearson) < 1 else float("inf")
    strength = "strong" if abs(pearson) >= 0.7 else ("moderate" if abs(pearson) >= 0.4 else "weak")
    return {"n_pairs": n, "pearson_r": round(pearson, 4), "spearman_rho": round(spearman, 4), "t_statistic": round(t, 3) if math.isfinite(t) else None, "strength": strength, "direction": "positive" if pearson > 0 else "negative", "pairs": [{"key": f"{k[0]}:{k[1]}", "x": kx[k], "y": ky[k]} for k in common][:200], "caveat": "Correlation does not imply causation."}


def anomaly(rows: List[Dict[str, Any]], z_threshold: float = 2.5, iqr_k: float = 1.5) -> Dict[str, Any]:
    v = _vals(rows)
    if v.size < 5:
        raise ValidationFailed("Anomaly detection needs at least 5 observations")
    mean, sd = float(v.mean()), float(v.std(ddof=1))
    q1, q3 = np.percentile(v, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - iqr_k * iqr, q3 + iqr_k * iqr
    items = []
    for r, x in zip(rows, v):
        z = (x - mean) / sd if sd else 0.0
        flags = []
        if abs(z) >= z_threshold:
            flags.append("z_score")
        if x < lo or x > hi:
            flags.append("iqr")
        if flags:
            items.append({"label": r.get("label"), "year": r.get("year"), "value": round(float(x), 4), "z": round(float(z), 3), "rules": flags, "direction": "high" if x > mean else "low"})
    return {"n": int(v.size), "mean": round(mean, 4), "std": round(sd, 4), "iqr_bounds": [round(float(lo), 4), round(float(hi), 4)], "anomalies": sorted(items, key=lambda i: -abs(i["z"])), "anomaly_rate_pct": round(100 * len(items) / v.size, 2)}


def forecast(rows: List[Dict[str, Any]], horizon: int = 5, alpha: float = 0.6, beta: float = 0.3) -> Dict[str, Any]:
    years, vals = _annual(rows)
    if years.size < 4:
        raise ValidationFailed("Forecast needs at least 4 annual points")
    level, trend_ = vals[0], vals[1] - vals[0]
    fitted = [level]
    for x in vals[1:]:
        prev_level = level
        level = alpha * x + (1 - alpha) * (level + trend_)
        trend_ = beta * (level - prev_level) + (1 - beta) * trend_
        fitted.append(level)
    resid = vals[1:] - np.array(fitted[:-1]) - trend_
    sigma = float(np.std(resid, ddof=1)) if resid.size > 1 else float(abs(trend_)) or 1.0
    step = float(years[-1] - years[-2]) if years.size > 1 else 1.0
    out = []
    for h in range(1, horizon + 1):
        point = level + h * trend_
        width = 1.96 * sigma * math.sqrt(h)
        out.append({"year": int(years[-1] + h * step), "value": round(float(point), 4), "low": round(float(point - width), 4), "high": round(float(point + width), 4), "value_kind": "MODELLED"})
    mape = float(np.mean(np.abs((vals[1:] - np.array(fitted[:-1])) / np.where(vals[1:] == 0, 1, vals[1:])))) * 100
    return {"method": "Holt linear exponential smoothing", "alpha": alpha, "beta": beta, "last_observed": {"year": int(years[-1]), "value": round(float(vals[-1]), 4)}, "trend_per_period": round(float(trend_), 4), "in_sample_mape_pct": round(mape, 2), "forecast": out, "uncertainty": "95% interval from residual std × sqrt(horizon); UNCERTAINTY grows with horizon", "value_kind": "MODELLED"}


def risk_score(indicators: List[Dict[str, Any]]) -> Dict[str, Any]:
    """indicators: [{code, weight, higher_is_riskier, values: [{label, value}]}]"""
    if not indicators:
        raise ValidationFailed("Provide at least one indicator")
    labels: set = set()
    for ind in indicators:
        labels.update(v["label"] for v in ind.get("values", []))
    total_w = sum(float(i.get("weight", 1.0)) for i in indicators) or 1.0
    scores: Dict[str, float] = {l: 0.0 for l in labels}
    components: Dict[str, Dict[str, float]] = {l: {} for l in labels}
    for ind in indicators:
        vals = {v["label"]: float(v["value"]) for v in ind.get("values", [])}
        if not vals:
            continue
        lo, hi = min(vals.values()), max(vals.values())
        for l in labels:
            if l not in vals:
                continue
            norm = (vals[l] - lo) / (hi - lo) if hi > lo else 0.5
            if not ind.get("higher_is_riskier", True):
                norm = 1 - norm
            w = float(ind.get("weight", 1.0)) / total_w
            scores[l] += 100 * norm * w
            components[l][ind["code"]] = round(100 * norm, 2)
    items = sorted([{"label": l, "risk_score": round(s, 2), "components": components[l], "band": "high" if s >= 66 else ("medium" if s >= 33 else "low")} for l, s in scores.items()], key=lambda x: -x["risk_score"])
    return {"weights": {i["code"]: round(float(i.get("weight", 1.0)) / total_w, 3) for i in indicators}, "items": items, "value_kind": "MODELLED", "note": "Relative index within the supplied set; weights are ASSUMPTIONS"}


def timeseries(rows: List[Dict[str, Any]], window: int = 3) -> Dict[str, Any]:
    years, vals = _annual(rows)
    if years.size < 2:
        raise ValidationFailed("Time-series profile needs at least 2 annual points")
    yoy = [None] + [round(float(100 * (vals[i] - vals[i - 1]) / vals[i - 1]), 3) if vals[i - 1] else None for i in range(1, vals.size)]
    ma = [round(float(np.mean(vals[max(0, i - window + 1) : i + 1])), 4) for i in range(vals.size)]
    span = float(years[-1] - years[0])
    cagr = ((vals[-1] / vals[0]) ** (1 / span) - 1) * 100 if span > 0 and vals[0] > 0 and vals[-1] > 0 else None
    return {"years": years.astype(int).tolist(), "values": [round(float(v), 4) for v in vals], "yoy_change_pct": yoy, "moving_average": ma, "window": window, "cagr_pct": round(float(cagr), 3) if cagr is not None else None, "total_change_pct": round(float(100 * (vals[-1] - vals[0]) / vals[0]), 3) if vals[0] else None}


def spatial_aggregate(db: Session, dataset_version_id: uuid.UUID, variable_code: Optional[str], level: str, year: Optional[int]) -> Dict[str, Any]:
    stmt = select(AdminUnit.id, AdminUnit.name, AdminUnit.level, func.count(Observation.id), func.avg(Observation.value), func.sum(Observation.value), func.min(Observation.value), func.max(Observation.value)).join(Observation, Observation.admin_unit_id == AdminUnit.id).where(Observation.dataset_version_id == dataset_version_id)
    if variable_code:
        stmt = stmt.where(Observation.variable_code == variable_code)
    if year:
        stmt = stmt.where(func.extract("year", Observation.period_start) == year)
    rows = db.execute(stmt.group_by(AdminUnit.id, AdminUnit.name, AdminUnit.level).order_by(func.sum(Observation.value).desc())).all()
    units = [{"admin_unit_id": str(i), "name": n, "level": l.value, "n": int(c), "mean": round(float(a), 4), "sum": round(float(s), 4), "min": round(float(mn), 4), "max": round(float(mx), 4)} for i, n, l, c, a, s, mn, mx in rows]
    # roll up to requested level via parent chain
    if level != "unit":
        rolled: Dict[str, Dict[str, Any]] = {}
        for u in units:
            cur = db.get(AdminUnit, uuid.UUID(u["admin_unit_id"]))
            while cur is not None and cur.level.value != level and cur.parent_id:
                cur = db.get(AdminUnit, cur.parent_id)
            if cur is None or cur.level.value != level:
                continue
            r = rolled.setdefault(str(cur.id), {"admin_unit_id": str(cur.id), "name": cur.name, "level": cur.level.value, "n": 0, "sum": 0.0, "children": 0})
            r["n"] += u["n"]
            r["sum"] = round(r["sum"] + u["sum"], 4)
            r["children"] += 1
        units = sorted(rolled.values(), key=lambda x: -x["sum"])
    return {"level": level, "items": units, "unlinked_note": "Observations without an admin_unit link are excluded"}


# ---------------------------------------------------------------------------
# Orchestration + persistence
# ---------------------------------------------------------------------------
def run_analysis(db: Session, *, analysis_type: str, params: Dict[str, Any], user_id: Optional[uuid.UUID], workspace_id: Optional[uuid.UUID] = None, title: Optional[str] = None) -> Dict[str, Any]:
    if analysis_type not in ANALYSIS_TYPES:
        raise ValidationFailed(f"analysis_type must be one of {ANALYSIS_TYPES}")
    mvs = ensure_models(db)
    mv = mvs[analysis_type]
    run = AnalyticsRun(analysis_type=analysis_type, title=title or f"{analysis_type} analysis", parameters=params, dataset_version_id=params.get("dataset_version_id"), model_version_id=mv.id, admin_unit_id=params.get("admin_unit_id"), created_by=user_id, workspace_id=workspace_id, status="running")
    db.add(run)
    db.flush()
    try:
        provenance: Dict[str, Any] = {}
        rows: List[Dict[str, Any]] = []
        if analysis_type not in ("risk_score", "spatial_aggregate"):
            rows, provenance = load_series(db, dataset_version_id=params.get("dataset_version_id"), variable_code=params.get("variable_code"), admin_unit_id=params.get("admin_unit_id"), indicator_code=params.get("indicator_code"), inline=params.get("data"))
        if analysis_type == "descriptive":
            result = descriptive(rows)
        elif analysis_type == "trend":
            result = trend(rows)
        elif analysis_type == "compare":
            result = compare(rows, latest_only=params.get("latest_only", True))
        elif analysis_type == "correlation":
            rows_y, prov_y = load_series(db, dataset_version_id=params.get("dataset_version_id_y") or params.get("dataset_version_id"), variable_code=params.get("variable_code_y"), admin_unit_id=params.get("admin_unit_id"), indicator_code=params.get("indicator_code_y"), inline=params.get("data_y"))
            provenance = {"x": provenance, "y": prov_y}
            result = correlation(rows, rows_y)
        elif analysis_type == "anomaly":
            result = anomaly(rows, float(params.get("z_threshold", 2.5)), float(params.get("iqr_k", 1.5)))
        elif analysis_type == "forecast":
            result = forecast(rows, int(params.get("horizon", 5)), float(params.get("alpha", 0.6)), float(params.get("beta", 0.3)))
        elif analysis_type == "timeseries":
            result = timeseries(rows, int(params.get("window", 3)))
        elif analysis_type == "risk_score":
            result = risk_score(params.get("indicators") or [])
            provenance = {"source": "inline_indicators"}
        else:
            result = spatial_aggregate(db, params["dataset_version_id"], params.get("variable_code"), params.get("level", "district"), params.get("year"))
            provenance = {"source": "dataset_version", "dataset_version_id": str(params["dataset_version_id"])}
        demo = any(r.get("is_demo") for r in rows)
        kinds = sorted({r.get("kind", "OBSERVED") for r in rows}) or ["OBSERVED"]
        result["input_value_kinds"] = kinds
        result["output_value_kind"] = result.get("value_kind", "MODELLED" if analysis_type in ("forecast", "risk_score", "trend") else "OBSERVED")
        run.result = result
        run.status = "completed"
        rec = evidence_service.create_recommendation(db, kind="analytics", title=run.title, statement=_statement(analysis_type, result), created_by=user_id, confidence=None, limitations=mv.limitations, model_version_id=mv.id, is_demo=demo)
        run.recommendation_id = rec.id
        evidence_service.link(db, NodeType.ANALYTICS_RUN, run.id, NodeType.RECOMMENDATION, rec.id, "produced")
        evidence_service.link(db, NodeType.ANALYTICS_RUN, run.id, NodeType.MODEL_VERSION, mv.id, "uses_model")
        if provenance.get("dataset_version_id"):
            evidence_service.add_evidence(db, rec, source_type=NodeType.DATASET_VERSION, source_id=uuid.UUID(provenance["dataset_version_id"]), label=f"Dataset version {provenance['dataset_version_id'][:8]} ({provenance.get('rows', 0)} observations)", value_kind=kinds[0])
        for k in ("x", "y"):
            if isinstance(provenance.get(k), dict) and provenance[k].get("dataset_version_id"):
                evidence_service.add_evidence(db, rec, source_type=NodeType.DATASET_VERSION, source_id=uuid.UUID(provenance[k]["dataset_version_id"]), label=f"Series {k}: dataset version", value_kind="OBSERVED")
        for dv in provenance.get("dataset_version_ids", []) or []:
            evidence_service.add_evidence(db, rec, source_type=NodeType.DATASET_VERSION, source_id=uuid.UUID(dv), label="Indicator source dataset version", value_kind="OBSERVED")
        if not rec.evidence:
            evidence_service.add_evidence(db, rec, source_type=NodeType.ANALYTICS_RUN, source_id=run.id, label=f"Inline input data ({len(rows)} rows)", value_kind=kinds[0])
        db.commit()
        return {"run_id": str(run.id), "recommendation_id": str(rec.id), "analysis_type": analysis_type, "model_version": {"id": str(mv.id), "version": mv.version, "algorithm": mv.algorithm, "limitations": mv.limitations}, "provenance": provenance, "is_demo": demo, "result": result}
    except Exception as exc:
        db.rollback()
        run = db.get(AnalyticsRun, run.id)
        if run:
            run.status = "failed"
            run.error = str(exc)[:1000]
            db.commit()
        raise


def _statement(t: str, r: Dict[str, Any]) -> str:
    if t == "trend":
        return f"Series is {r['direction']} at {r['slope_per_year']} per year (R²={r['r_squared']})."
    if t == "forecast":
        f = r["forecast"][-1]
        return f"Projected value {f['value']} by {f['year']} (95% interval {f['low']}–{f['high']}) — MODELLED estimate."
    if t == "anomaly":
        return f"{len(r['anomalies'])} anomalous observation(s) detected ({r['anomaly_rate_pct']}%)."
    if t == "correlation":
        return f"{r['strength'].capitalize()} {r['direction']} correlation (Pearson r={r['pearson_r']}, n={r['n_pairs']})."
    if t == "compare":
        top = r["items"][0] if r["items"] else None
        return f"Highest value: {top['label']} ({top['value']})." if top else "No groups."
    if t == "risk_score":
        top = r["items"][0] if r["items"] else None
        return f"Highest composite risk: {top['label']} ({top['risk_score']}/100)." if top else "No items."
    if t == "descriptive":
        return f"n={r['n']}, mean={r['mean']}, median={r['median']}, std={r['std']}."
    if t == "timeseries":
        return f"Total change {r['total_change_pct']}% (CAGR {r['cagr_pct']}%)."
    return f"{len(r.get('items', []))} spatial units aggregated."


def list_runs(db: Session, user_id: Optional[uuid.UUID], limit: int = 50) -> List[Dict[str, Any]]:
    stmt = select(AnalyticsRun).order_by(AnalyticsRun.created_at.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(AnalyticsRun.created_by == user_id)
    return [{"id": str(r.id), "analysis_type": r.analysis_type, "title": r.title, "status": r.status, "created_at": r.created_at.isoformat(), "recommendation_id": str(r.recommendation_id) if r.recommendation_id else None, "error": r.error} for r in db.scalars(stmt).all()]


def get_run(db: Session, run_id: uuid.UUID) -> Dict[str, Any]:
    r = db.get(AnalyticsRun, run_id)
    if not r:
        raise NotFoundError("Run not found")
    return {"id": str(r.id), "analysis_type": r.analysis_type, "title": r.title, "status": r.status, "parameters": r.parameters, "result": r.result, "error": r.error, "created_at": r.created_at.isoformat(), "recommendation_id": str(r.recommendation_id) if r.recommendation_id else None, "model_version_id": str(r.model_version_id) if r.model_version_id else None}


def list_models(db: Session) -> List[Dict[str, Any]]:
    ensure_models(db)
    out = []
    for m in db.scalars(select(AnalysisModel).order_by(AnalysisModel.model_type, AnalysisModel.name)).all():
        out.append({"id": str(m.id), "name": m.name, "slug": m.slug, "type": m.model_type, "objective": m.objective, "is_active": m.is_active, "versions": [{"id": str(v.id), "version": v.version, "algorithm": v.algorithm, "features": v.features, "parameters": v.parameters, "evaluation": v.evaluation, "limitations": v.limitations, "is_default": v.is_default, "training_dataset_version_id": str(v.training_dataset_version_id) if v.training_dataset_version_id else None} for v in m.versions]})
    return out
