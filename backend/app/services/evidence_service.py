from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.datasets import Dataset, DatasetVersion
from app.models.gis import AdminUnit, GISLayer, RSProduct
from app.models.intelligence import AIMessage, AnalysisModel, AnalyticsRun, Assumption, EvidenceItem, ModelVersion, NodeType, ProvenanceLink, Recommendation, Scenario, SimulationRun
from app.models.knowledge import Document, DocumentChunk, DocumentVersion, Policy


def create_recommendation(db: Session, *, kind: str, title: str, statement: str, created_by: Optional[uuid.UUID], confidence: Optional[float] = None, confidence_basis: Optional[str] = None, limitations: Optional[str] = None, assumptions: Optional[List[Dict[str, Any]]] = None, model_version_id: Optional[uuid.UUID] = None, scenario_id: Optional[uuid.UUID] = None, simulation_run_id: Optional[uuid.UUID] = None, is_demo: bool = False) -> Recommendation:
    rec = Recommendation(kind=kind, title=title[:500], statement=statement, created_by=created_by, confidence=confidence, confidence_basis=confidence_basis, limitations=limitations, assumptions=assumptions, model_version_id=model_version_id, scenario_id=scenario_id, simulation_run_id=simulation_run_id, is_demo=is_demo)
    db.add(rec)
    db.flush()
    if model_version_id:
        link(db, NodeType.RECOMMENDATION, rec.id, NodeType.MODEL_VERSION, model_version_id, "produced_by")
    if scenario_id:
        link(db, NodeType.RECOMMENDATION, rec.id, NodeType.SCENARIO, scenario_id, "evaluates")
    if simulation_run_id:
        link(db, NodeType.RECOMMENDATION, rec.id, NodeType.SIMULATION_RUN, simulation_run_id, "derived_from")
    return rec


def add_evidence(db: Session, rec: Recommendation, *, source_type: NodeType, source_id: Optional[uuid.UUID], label: str, excerpt: Optional[str] = None, locator: Optional[str] = None, score: Optional[float] = None, value_kind: str = "OBSERVED", rank: Optional[int] = None) -> EvidenceItem:
    ev = EvidenceItem(recommendation_id=rec.id, rank=rank if rank is not None else len(rec.evidence), source_type=source_type, source_id=source_id, label=label[:500], excerpt=excerpt, locator=locator, score=score, value_kind=value_kind)
    db.add(ev)
    db.flush()
    link(db, NodeType.RECOMMENDATION, rec.id, NodeType.EVIDENCE, ev.id, "supported_by")
    if source_id:
        link(db, NodeType.EVIDENCE, ev.id, source_type, source_id, "cites")
        _extend_provenance(db, source_type, source_id)
    return ev


def link(db: Session, from_type: NodeType, from_id: uuid.UUID, to_type: NodeType, to_id: uuid.UUID, relation: str, detail: Optional[Dict[str, Any]] = None) -> None:
    exists = db.scalar(select(ProvenanceLink.id).where(ProvenanceLink.from_type == from_type, ProvenanceLink.from_id == from_id, ProvenanceLink.to_type == to_type, ProvenanceLink.to_id == to_id, ProvenanceLink.relation == relation))
    if not exists:
        db.add(ProvenanceLink(from_type=from_type, from_id=from_id, to_type=to_type, to_id=to_id, relation=relation, detail=detail))
        db.flush()


def _extend_provenance(db: Session, node_type: NodeType, node_id: uuid.UUID) -> None:
    """Materialise the intrinsic lineage of a source node so a trace can walk
    chunk → version → document, dataset_version → dataset, layer → dataset etc."""
    if node_type == NodeType.DOCUMENT_CHUNK:
        chunk = db.get(DocumentChunk, node_id)
        if chunk:
            link(db, NodeType.DOCUMENT_CHUNK, chunk.id, NodeType.DOCUMENT_VERSION, chunk.version_id, "part_of")
            link(db, NodeType.DOCUMENT_VERSION, chunk.version_id, NodeType.DOCUMENT, chunk.document_id, "version_of")
    elif node_type == NodeType.DOCUMENT_VERSION:
        v = db.get(DocumentVersion, node_id)
        if v:
            link(db, NodeType.DOCUMENT_VERSION, v.id, NodeType.DOCUMENT, v.document_id, "version_of")
    elif node_type == NodeType.DATASET_VERSION:
        v = db.get(DatasetVersion, node_id)
        if v:
            link(db, NodeType.DATASET_VERSION, v.id, NodeType.DATASET, v.dataset_id, "version_of")
    elif node_type == NodeType.GIS_LAYER:
        layer = db.get(GISLayer, node_id)
        if layer and layer.dataset_version_id:
            link(db, NodeType.GIS_LAYER, layer.id, NodeType.DATASET_VERSION, layer.dataset_version_id, "derived_from")
        elif layer and layer.dataset_id:
            link(db, NodeType.GIS_LAYER, layer.id, NodeType.DATASET, layer.dataset_id, "derived_from")
    elif node_type == NodeType.MODEL_VERSION:
        mv = db.get(ModelVersion, node_id)
        if mv:
            link(db, NodeType.MODEL_VERSION, mv.id, NodeType.MODEL, mv.model_id, "version_of")
            if mv.training_dataset_version_id:
                link(db, NodeType.MODEL_VERSION, mv.id, NodeType.DATASET_VERSION, mv.training_dataset_version_id, "trained_on")
    elif node_type == NodeType.SCENARIO:
        sc = db.get(Scenario, node_id)
        if sc:
            if sc.baseline_dataset_version_id:
                link(db, NodeType.SCENARIO, sc.id, NodeType.DATASET_VERSION, sc.baseline_dataset_version_id, "baseline_from")
            for a in sc.assumptions:
                link(db, NodeType.SCENARIO, sc.id, NodeType.ASSUMPTION, a.id, "assumes")
            if sc.admin_unit_id:
                link(db, NodeType.SCENARIO, sc.id, NodeType.ADMIN_UNIT, sc.admin_unit_id, "located_in")
    elif node_type == NodeType.SIMULATION_RUN:
        run = db.get(SimulationRun, node_id)
        if run:
            link(db, NodeType.SIMULATION_RUN, run.id, NodeType.SCENARIO, run.scenario_id, "runs")
            if run.model_version_id:
                link(db, NodeType.SIMULATION_RUN, run.id, NodeType.MODEL_VERSION, run.model_version_id, "uses_model")
            _extend_provenance(db, NodeType.SCENARIO, run.scenario_id)
            if run.model_version_id:
                _extend_provenance(db, NodeType.MODEL_VERSION, run.model_version_id)
    elif node_type == NodeType.RS_PRODUCT:
        prod = db.get(RSProduct, node_id)
        if prod and prod.model_version_id:
            link(db, NodeType.RS_PRODUCT, prod.id, NodeType.MODEL_VERSION, prod.model_version_id, "produced_by")


# ---------------------------------------------------------------------------
# Trace: BFS over provenance graph starting from a recommendation/evidence node
# ---------------------------------------------------------------------------
_LABEL_LOADERS = {
    NodeType.RECOMMENDATION: (Recommendation, lambda o: o.title),
    NodeType.EVIDENCE: (EvidenceItem, lambda o: o.label),
    NodeType.DOCUMENT: (Document, lambda o: o.title),
    NodeType.DOCUMENT_VERSION: (DocumentVersion, lambda o: f"v{o.version_number} · {o.file_name}"),
    NodeType.DOCUMENT_CHUNK: (DocumentChunk, lambda o: f"Chunk {o.chunk_index} (p.{o.page_start})"),
    NodeType.DATASET: (Dataset, lambda o: o.name),
    NodeType.DATASET_VERSION: (DatasetVersion, lambda o: f"v{o.version_number}"),
    NodeType.POLICY: (Policy, lambda o: o.title),
    NodeType.GIS_LAYER: (GISLayer, lambda o: o.name),
    NodeType.MODEL: (AnalysisModel, lambda o: o.name),
    NodeType.MODEL_VERSION: (ModelVersion, lambda o: f"{o.version} · {o.algorithm}"),
    NodeType.ASSUMPTION: (Assumption, lambda o: o.statement[:120]),
    NodeType.SCENARIO: (Scenario, lambda o: o.name),
    NodeType.SIMULATION_RUN: (SimulationRun, lambda o: f"Run {str(o.id)[:8]} ({o.status})"),
    NodeType.ANALYTICS_RUN: (AnalyticsRun, lambda o: o.title or o.analysis_type),
    NodeType.RS_PRODUCT: (RSProduct, lambda o: o.product_type),
    NodeType.AI_MESSAGE: (AIMessage, lambda o: o.content[:80]),
    NodeType.ADMIN_UNIT: (AdminUnit, lambda o: f"{o.name} ({o.level.value})"),
}


def _node_payload(db: Session, node_type: NodeType, node_id: uuid.UUID) -> Dict[str, Any]:
    loader = _LABEL_LOADERS.get(node_type)
    payload: Dict[str, Any] = {"id": str(node_id), "type": node_type.value, "label": node_type.value, "attributes": {}}
    if not loader:
        return payload
    model, label_fn = loader
    obj = db.get(model, node_id)
    if obj is None:
        payload["label"] = f"{node_type.value} (deleted)"
        payload["missing"] = True
        return payload
    payload["label"] = label_fn(obj)
    attrs = payload["attributes"]
    for k in ("created_at", "updated_at", "version_number", "version", "algorithm", "value_kind", "confidence", "status", "is_demo", "score", "locator", "excerpt", "statement", "value", "low", "high", "unit", "basis", "publication_date", "source", "license", "checksum_sha256", "processing_status", "acquisition_date", "level", "code"):
        if hasattr(obj, k):
            v = getattr(obj, k)
            if v is None:
                continue
            attrs[k] = v.value if hasattr(v, "value") and not isinstance(v, (int, float)) else (v.isoformat() if hasattr(v, "isoformat") else v)
    return payload


def trace(db: Session, node_type: NodeType, node_id: uuid.UUID, max_depth: int = 6, max_nodes: int = 300) -> Dict[str, Any]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    visited: Set[Tuple[str, str]] = set()
    frontier: List[Tuple[NodeType, uuid.UUID, int]] = [(node_type, node_id, 0)]
    while frontier and len(nodes) < max_nodes:
        t, i, depth = frontier.pop(0)
        key = (t.value, str(i))
        if key in visited:
            continue
        visited.add(key)
        nodes[str(i)] = {**_node_payload(db, t, i), "depth": depth}
        if depth >= max_depth:
            continue
        links = db.scalars(select(ProvenanceLink).where(or_(ProvenanceLink.from_id == i, ProvenanceLink.to_id == i))).all()
        for lnk in links:
            edges.append({"from": str(lnk.from_id), "to": str(lnk.to_id), "relation": lnk.relation, "detail": lnk.detail})
            # traverse downstream (from -> to) fully, and one step upstream so sibling context appears
            if lnk.from_id == i and (lnk.to_type.value, str(lnk.to_id)) not in visited:
                frontier.append((lnk.to_type, lnk.to_id, depth + 1))
            elif lnk.to_id == i and depth == 0 and (lnk.from_type.value, str(lnk.from_id)) not in visited:
                frontier.append((lnk.from_type, lnk.from_id, depth + 1))
    unique_edges = {(e["from"], e["to"], e["relation"]): e for e in edges}
    return {"root": {"type": node_type.value, "id": str(node_id)}, "nodes": list(nodes.values()), "edges": [e for e in unique_edges.values() if e["from"] in nodes and e["to"] in nodes]}


def get_recommendation(db: Session, rec_id: uuid.UUID) -> Recommendation:
    rec = db.get(Recommendation, rec_id)
    if not rec:
        raise NotFoundError("Recommendation not found")
    return rec


def explain(db: Session, rec: Recommendation) -> Dict[str, Any]:
    """Human-readable 'why did the system produce this?' summary."""
    ev = [
        {"rank": e.rank, "type": e.source_type.value, "source_id": str(e.source_id) if e.source_id else None, "label": e.label, "excerpt": e.excerpt, "locator": e.locator, "score": e.score, "value_kind": e.value_kind}
        for e in sorted(rec.evidence, key=lambda x: x.rank)
    ]
    kinds = sorted({e["value_kind"] for e in ev})
    steps = [
        f"The output '{rec.title}' is of kind '{rec.kind}' and was generated on {rec.created_at.isoformat()}.",
        f"It rests on {len(ev)} evidence item(s) of type(s): {', '.join(sorted({e['type'] for e in ev})) or 'none'}.",
    ]
    if rec.model_version_id:
        mv = db.get(ModelVersion, rec.model_version_id)
        if mv:
            steps.append(f"Computed by model version {mv.version} ({mv.algorithm}); limitations: {mv.limitations or 'not recorded'}.")
    if rec.assumptions:
        steps.append(f"{len(rec.assumptions)} explicit assumption(s) were applied and are listed below.")
    if rec.confidence is not None:
        steps.append(f"Confidence {rec.confidence:.2f} — basis: {rec.confidence_basis or 'heuristic'}.")
    if rec.limitations:
        steps.append(f"Limitations: {rec.limitations}")
    if rec.is_demo:
        steps.append("This output was produced from Demo / Synthetic Data and is not an official statistic.")
    return {"recommendation": {"id": str(rec.id), "kind": rec.kind, "title": rec.title, "statement": rec.statement, "confidence": rec.confidence, "confidence_basis": rec.confidence_basis, "limitations": rec.limitations, "assumptions": rec.assumptions, "created_at": rec.created_at.isoformat(), "is_demo": rec.is_demo}, "evidence": ev, "value_kinds_present": kinds, "explanation": steps, "disclaimer": "Decision-support output. Not an official government decision."}
