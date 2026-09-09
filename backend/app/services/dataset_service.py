from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import service as audit
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from app.core.permissions import P
from app.models.datasets import DataSource, Dataset, DatasetStatus, DatasetVariable, DatasetVersion, Observation
from app.models.gis import AdminUnit
from app.models.identity import User
from app.models.platform import Approval
from app.notifications.service import notify
from app.schemas.datasets import DatasetCreate, DatasetUpdate
from app.search import indexer
from app.services.document_service import unique_slug
from app.storage.service import build_key, get_storage, sha256_bytes
from app.storage.validation import validate_upload

_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def can_view(ds: Dataset, user: Optional[User], perms: Set[str]) -> bool:
    if ds.deleted_at is not None:
        return False
    if user is None:
        return ds.status == DatasetStatus.PUBLISHED and ds.access_level in ("public", "open")
    if user.is_superuser or ds.owner_id == user.id or P.DATASET_APPROVE in perms:
        return True
    if ds.access_level == "restricted":
        return ds.organization_id is not None and ds.organization_id == user.primary_organization_id
    return ds.status in (DatasetStatus.PUBLISHED, DatasetStatus.APPROVED) or P.DATASET_UPDATE in perms


def can_edit(ds: Dataset, user: User, perms: Set[str]) -> bool:
    return user.is_superuser or ds.owner_id == user.id or P.DATASET_APPROVE in perms or (P.DATASET_UPDATE in perms and ds.organization_id == user.primary_organization_id)


def get_dataset(db: Session, ds_id: uuid.UUID, user: Optional[User], perms: Set[str]) -> Dataset:
    ds = db.scalar(select(Dataset).options(selectinload(Dataset.versions), selectinload(Dataset.variables), selectinload(Dataset.source)).execution_options(populate_existing=True).where(Dataset.id == ds_id))
    if not ds or not can_view(ds, user, perms):
        raise NotFoundError("Dataset not found")
    return ds


def create_dataset(db: Session, payload: DatasetCreate, user: User, request: Optional[Request] = None) -> Dataset:
    data = payload.model_dump(exclude={"variables"})
    if data.get("source_id") and not db.get(DataSource, data["source_id"]):
        raise ValidationFailed("Data source not found")
    ds = Dataset(**data, slug=unique_slug(db, Dataset, payload.name), owner_id=user.id)
    db.add(ds)
    db.flush()
    for v in payload.variables:
        db.add(DatasetVariable(dataset_id=ds.id, **v.model_dump()))
    audit.record(db, "dataset.create", user=user, resource_type="dataset", resource_id=ds.id, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    return get_dataset(db, ds.id, user, {P.DATASET_APPROVE})


def update_dataset(db: Session, ds: Dataset, payload: DatasetUpdate, user: User, perms: Set[str], request: Optional[Request] = None) -> Dataset:
    if not can_edit(ds, user, perms):
        raise ForbiddenError("You cannot edit this dataset")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(ds, k, v)
    audit.record(db, "dataset.update", user=user, resource_type="dataset", resource_id=ds.id, detail={"fields": list(changes)}, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    return ds


# ---------------------------------------------------------------------------
# Tabular ingestion → schema snapshot + observations
# ---------------------------------------------------------------------------
def _parse_period(value: str) -> Tuple[Optional[date], Optional[date]]:
    v = (value or "").strip()
    m = _DATE_RE.match(v)
    if not m:
        return None, None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    if d:
        dt = date(y, int(mo), int(d))
        return dt, dt
    if mo:
        start = date(y, int(mo), 1)
        end = date(y + (int(mo) == 12), (int(mo) % 12) + 1, 1)
        return start, end
    return date(y, 1, 1), date(y, 12, 31)


def _read_rows(data: bytes, mime: str) -> Tuple[List[str], List[Dict[str, str]]]:
    if mime == "text/csv" or mime == "text/plain":
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames or []), rows
    if mime.endswith("spreadsheetml.sheet"):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(next(it, []))]
        rows = []
        for r in it:
            if r is None or all(c is None for c in r):
                continue
            rows.append({header[i]: ("" if c is None else str(c)) for i, c in enumerate(r) if i < len(header)})
        return header, rows
    return [], []


def _profile(header: List[str], rows: List[Dict[str, str]]) -> Dict[str, Any]:
    cols: Dict[str, Any] = {}
    for h in header:
        vals = [r.get(h, "") for r in rows]
        nonempty = [v for v in vals if v not in ("", None)]
        numeric = []
        for v in nonempty:
            try:
                numeric.append(float(str(v).replace(",", "")))
            except ValueError:
                pass
        kind = "number" if nonempty and len(numeric) >= 0.9 * len(nonempty) else "string"
        col: Dict[str, Any] = {"type": kind, "non_null": len(nonempty), "null": len(vals) - len(nonempty), "distinct": len(set(nonempty))}
        if kind == "number" and numeric:
            col.update({"min": min(numeric), "max": max(numeric), "mean": round(sum(numeric) / len(numeric), 4)})
        else:
            col["sample"] = list(dict.fromkeys(nonempty))[:5]
        cols[h] = col
    return {"columns": cols, "row_count": len(rows), "column_count": len(header)}


def _find_col(header: List[str], candidates: Tuple[str, ...]) -> Optional[str]:
    lower = {h.lower().strip(): h for h in header}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def ingest_observations(db: Session, ds: Dataset, version: DatasetVersion, header: List[str], rows: List[Dict[str, str]], is_demo: bool = False) -> int:
    """Long format: variable/indicator, value, geography/admin_code, period/year.
    Wide format: geography + period columns with one numeric column per variable."""
    var_col = _find_col(header, ("variable", "variable_code", "indicator", "indicator_code", "code"))
    val_col = _find_col(header, ("value", "amount", "val"))
    geo_col = _find_col(header, ("geography", "admin_unit", "district", "state", "region", "area_name", "name"))
    code_col = _find_col(header, ("admin_code", "lgd_code", "unit_code", "geo_code"))
    per_col = _find_col(header, ("period", "year", "date", "period_start"))
    unit_col = _find_col(header, ("unit", "units"))
    kind_col = _find_col(header, ("value_kind", "kind"))
    units_by_code = {u.code: u.id for u in db.scalars(select(AdminUnit)).all()} if code_col else {}
    units_by_name = {u.name.lower(): u.id for u in db.scalars(select(AdminUnit)).all()} if geo_col else {}
    db.execute(delete(Observation).where(Observation.dataset_version_id == version.id))
    known_vars = {v.code: v for v in ds.variables}
    count = 0
    batch: List[Observation] = []

    def add(var: str, value: str, row: Dict[str, str]) -> None:
        nonlocal count
        try:
            val = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return
        p_start, p_end = _parse_period(row.get(per_col, "")) if per_col else (None, None)
        au = None
        if code_col and row.get(code_col):
            au = units_by_code.get(str(row[code_col]).strip())
        if au is None and geo_col and row.get(geo_col):
            au = units_by_name.get(str(row[geo_col]).strip().lower())
        unit = row.get(unit_col) if unit_col else (known_vars[var].unit if var in known_vars else None)
        kind = (row.get(kind_col) or "OBSERVED").upper() if kind_col else "OBSERVED"
        if kind not in ("OBSERVED", "MODELLED", "ASSUMPTION", "SCENARIO"):
            kind = "OBSERVED"
        batch.append(Observation(dataset_version_id=version.id, dataset_id=ds.id, variable_code=var[:80], admin_unit_id=au, geography_label=(row.get(geo_col) if geo_col else None), period_start=p_start, period_end=p_end, value=val, unit=unit, value_kind=kind, is_demo=is_demo))
        count += 1
        if var not in known_vars:
            v = DatasetVariable(dataset_id=ds.id, code=var[:80], name=var[:255], unit=unit, data_type="number")
            db.add(v)
            known_vars[var] = v

    if var_col and val_col:
        for r in rows:
            if r.get(var_col):
                add(str(r[var_col]).strip(), r.get(val_col, ""), r)
    else:
        reserved = {c for c in (geo_col, code_col, per_col, unit_col, kind_col) if c}
        numeric_cols = [h for h in header if h not in reserved]
        for r in rows:
            for h in numeric_cols:
                if r.get(h) not in ("", None):
                    add(h, r[h], r)
    for i in range(0, len(batch), 1000):
        db.add_all(batch[i : i + 1000])
        db.flush()
    return count


def upload_version(db: Session, ds: Dataset, *, data: bytes, filename: str, declared_mime: Optional[str], user: User, perms: Set[str], change_note: Optional[str], version_label: Optional[str], request: Optional[Request] = None) -> DatasetVersion:
    if not can_edit(ds, user, perms):
        raise ForbiddenError("You cannot upload to this dataset")
    mime = validate_upload(data, filename, declared_mime)
    checksum = sha256_bytes(data)
    if db.scalar(select(DatasetVersion.id).where(DatasetVersion.dataset_id == ds.id, DatasetVersion.checksum_sha256 == checksum)):
        raise ConflictError("Identical file already uploaded for this dataset")
    next_no = (db.scalar(select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == ds.id)) or 0) + 1
    key = build_key(f"datasets/{ds.id}", filename)
    get_storage().put(key, data, mime)
    version = DatasetVersion(dataset_id=ds.id, version_number=next_no, version_label=version_label, change_note=change_note, file_name=filename[:500], storage_key=key, mime_type=mime, file_size=len(data), checksum_sha256=checksum, uploaded_by=user.id, processing_status="PROCESSING")
    db.add(version)
    db.flush()
    try:
        header, rows = _read_rows(data, mime)
        if header:
            profile = _profile(header, rows)
            version.row_count = profile["row_count"]
            version.column_count = profile["column_count"]
            n = ingest_observations(db, ds, version, header, rows, is_demo=ds.is_demo)
            version.schema_snapshot = {**profile, "observations_ingested": n}
        else:
            version.schema_snapshot = {"note": f"No tabular profiler for {mime}; file stored as-is"}
        version.processing_status = "READY"
        version.processed_at = _now()
    except Exception as exc:
        version.processing_status = "FAILED"
        version.processing_error = str(exc)[:2000]
    ds.current_version_id = version.id
    if not ds.format:
        ds.format = {"text/csv": "CSV", "application/geo+json": "GeoJSON", "application/zip": "Shapefile/ZIP", "image/tiff": "GeoTIFF", "application/json": "JSON"}.get(mime, mime.split("/")[-1].upper()[:20])
    audit.record(db, "dataset.upload_version", user=user, resource_type="dataset", resource_id=ds.id, detail={"version": next_no, "mime": mime, "size": len(data), "sha256": checksum, "status": version.processing_status}, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    db.refresh(version)
    return version


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------
def submit(db: Session, ds: Dataset, user: User, perms: Set[str], request: Optional[Request] = None) -> Dataset:
    if not can_edit(ds, user, perms):
        raise ForbiddenError("You cannot submit this dataset")
    if ds.status not in (DatasetStatus.DRAFT, DatasetStatus.REJECTED):
        raise ConflictError(f"Dataset in status {ds.status.value} cannot be submitted")
    ds.status = DatasetStatus.PENDING_APPROVAL
    db.add(Approval(target_type="dataset", target_id=ds.id, title=f"Approve dataset: {ds.name}", requested_by=user.id))
    audit.record(db, "dataset.submit", user=user, resource_type="dataset", resource_id=ds.id, request=request)
    db.commit()
    return ds


def approve(db: Session, ds: Dataset, approver: User, decision: str, note: Optional[str], request: Optional[Request] = None) -> Dataset:
    if ds.status != DatasetStatus.PENDING_APPROVAL:
        raise ConflictError("Dataset is not pending approval")
    approval = db.scalar(select(Approval).where(Approval.target_type == "dataset", Approval.target_id == ds.id, Approval.status == "pending").order_by(Approval.created_at.desc()))
    if decision == "approve":
        ds.status = DatasetStatus.APPROVED
        ds.approved_by = approver.id
        outcome = "approved"
    else:
        ds.status = DatasetStatus.REJECTED
        outcome = "rejected"
    if approval:
        approval.status = outcome
        approval.decided_by = approver.id
        approval.decided_at = _now()
        approval.decision_note = note
    notify(db, ds.owner_id, "approval", f"Dataset {outcome}", f"{ds.name}: {note or ''}".strip(), link=f"/app/datasets/{ds.id}", email=True)
    audit.record(db, f"dataset.{outcome}", user=approver, resource_type="dataset", resource_id=ds.id, detail={"note": note}, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    return ds


def publish(db: Session, ds: Dataset, user: User, access_level: Optional[str], request: Optional[Request] = None) -> Dataset:
    if ds.status not in (DatasetStatus.APPROVED, DatasetStatus.PUBLISHED):
        raise ConflictError("Only approved datasets can be published")
    ds.status = DatasetStatus.PUBLISHED
    if access_level:
        ds.access_level = access_level
    audit.record(db, "dataset.publish", user=user, resource_type="dataset", resource_id=ds.id, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    return ds


def archive(db: Session, ds: Dataset, user: User, perms: Set[str], request: Optional[Request] = None) -> Dataset:
    if not (user.is_superuser or P.DATASET_DELETE in perms or ds.owner_id == user.id):
        raise ForbiddenError("You cannot archive this dataset")
    ds.status = DatasetStatus.ARCHIVED
    audit.record(db, "dataset.archive", user=user, resource_type="dataset", resource_id=ds.id, request=request)
    db.commit()
    indexer.index_dataset(db, ds)
    return ds


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def list_datasets(db: Session, user: Optional[User], perms: Set[str], *, q: Optional[str], category: Optional[str], status: Optional[str], geography: Optional[str], format_: Optional[str], source_id: Optional[uuid.UUID], organization_id: Optional[uuid.UUID], access_level: Optional[str], mine: bool, include_demo: bool, offset: int, limit: int, sort: Optional[str]) -> Tuple[List[Dataset], int]:
    stmt = select(Dataset).options(selectinload(Dataset.source)).where(Dataset.deleted_at.is_(None))
    if user is None:
        stmt = stmt.where(Dataset.status == DatasetStatus.PUBLISHED, Dataset.access_level.in_(["public", "open"]))
    elif not (user.is_superuser or P.DATASET_APPROVE in perms):
        stmt = stmt.where(or_(Dataset.owner_id == user.id, Dataset.status.in_([DatasetStatus.PUBLISHED, DatasetStatus.APPROVED]) & or_(Dataset.access_level != "restricted", Dataset.organization_id == user.primary_organization_id)))
    if mine and user:
        stmt = stmt.where(Dataset.owner_id == user.id)
    if q:
        stmt = stmt.where(or_(Dataset.name.ilike(f"%{q}%"), Dataset.description.ilike(f"%{q}%"), func.array_to_string(Dataset.keywords, " ").ilike(f"%{q}%")))
    if category:
        stmt = stmt.where(Dataset.category == category)
    if status:
        stmt = stmt.where(Dataset.status == status)
    if geography:
        stmt = stmt.where(Dataset.geography.ilike(f"%{geography}%"))
    if format_:
        stmt = stmt.where(Dataset.format.ilike(format_))
    if source_id:
        stmt = stmt.where(Dataset.source_id == source_id)
    if organization_id:
        stmt = stmt.where(Dataset.organization_id == organization_id)
    if access_level:
        stmt = stmt.where(Dataset.access_level == access_level)
    if not include_demo:
        stmt = stmt.where(Dataset.is_demo.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = Dataset.updated_at.desc()
    if sort:
        col = {"name": Dataset.name, "created_at": Dataset.created_at, "downloads": Dataset.download_count, "quality": Dataset.quality_score, "temporal_end": Dataset.temporal_end}.get(sort.lstrip("-"))
        if col is not None:
            order = col.desc().nullslast() if sort.startswith("-") else col.asc().nullsfirst()
    rows = db.scalars(stmt.order_by(order).offset(offset).limit(limit)).all()
    return rows, total


def observations(db: Session, ds: Dataset, *, variable_code: Optional[str], admin_unit_id: Optional[uuid.UUID], offset: int, limit: int) -> Tuple[List[Observation], int]:
    if not ds.current_version_id:
        return [], 0
    stmt = select(Observation).where(Observation.dataset_version_id == ds.current_version_id)
    if variable_code:
        stmt = stmt.where(Observation.variable_code == variable_code)
    if admin_unit_id:
        stmt = stmt.where(Observation.admin_unit_id == admin_unit_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Observation.variable_code, Observation.period_start.nullsfirst(), Observation.geography_label).offset(offset).limit(limit)).all()
    return rows, total


def facets(db: Session) -> Dict[str, Any]:
    base = select(Dataset).where(Dataset.deleted_at.is_(None)).subquery()
    out: Dict[str, Any] = {}
    for name, col in (("category", base.c.category), ("format", base.c.format), ("access_level", base.c.access_level), ("publisher", base.c.publisher), ("status", base.c.status)):
        out[name] = [{"value": v, "count": c} for v, c in db.execute(select(col, func.count()).where(col.is_not(None)).group_by(col).order_by(func.count().desc())).all()]
    out["sources"] = [{"id": str(s.id), "name": s.name, "is_official": s.is_official, "is_demo": s.is_demo} for s in db.scalars(select(DataSource).order_by(DataSource.name)).all()]
    return out


def pending_approval(db: Session, offset: int, limit: int) -> Tuple[List[Dataset], int]:
    stmt = select(Dataset).where(Dataset.status == DatasetStatus.PENDING_APPROVAL, Dataset.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return db.scalars(stmt.order_by(Dataset.updated_at.asc()).offset(offset).limit(limit)).all(), total
