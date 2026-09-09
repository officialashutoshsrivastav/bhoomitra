from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_optional, get_permissions, load_user_permissions, require_permissions
from app.audit import service as audit
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.permissions import P
from app.db.database import get_db
from app.models.datasets import DataSource, DatasetVersion, Observation
from app.models.identity import User
from app.schemas.common import Message, Page, PageParams
from app.schemas.datasets import DataSourceCreate, DataSourceOut, DatasetCreate, DatasetDetail, DatasetOut, DatasetUpdate, DatasetVersionOut, ObservationOut
from app.services import dataset_service as svc
from app.storage.service import get_storage, read_upload

router = APIRouter(prefix="/datasets", tags=["datasets"])


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: Optional[str] = Field(None, max_length=5000)


def _perms_for(request: Request, user: Optional[User], db: Session) -> set:
    if user is None:
        return set()
    return getattr(request.state, "permissions", None) or load_user_permissions(db, user)


@router.get("", response_model=Page[DatasetOut])
def list_datasets(request: Request, page: PageParams = Depends(), q: Annotated[Optional[str], Query(max_length=200)] = None, category: Optional[str] = None, status_filter: Annotated[Optional[str], Query(alias="status")] = None, geography: Optional[str] = None, format: Optional[str] = None, source_id: Optional[uuid.UUID] = None, organization_id: Optional[uuid.UUID] = None, access_level: Optional[str] = None, mine: bool = False, include_demo: bool = True, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    rows, total = svc.list_datasets(db, user, _perms_for(request, user, db), q=q, category=category, status=status_filter, geography=geography, format_=format, source_id=source_id, organization_id=organization_id, access_level=access_level, mine=mine, include_demo=include_demo, offset=page.offset, limit=page.page_size, sort=page.sort)
    return Page.build([DatasetOut.model_validate(d) for d in rows], total, page.page, page.page_size)


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    return svc.facets(db)


@router.get("/pending-approval", response_model=Page[DatasetOut])
def pending(page: PageParams = Depends(), user: User = Depends(require_permissions(P.DATASET_APPROVE)), db: Session = Depends(get_db)):
    rows, total = svc.pending_approval(db, page.offset, page.page_size)
    return Page.build([DatasetOut.model_validate(d) for d in rows], total, page.page, page.page_size)


@router.get("/sources", response_model=List[DataSourceOut])
def list_sources(db: Session = Depends(get_db)):
    return [DataSourceOut.model_validate(s) for s in db.scalars(select(DataSource).order_by(DataSource.name)).all()]


@router.post("/sources", response_model=DataSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(payload: DataSourceCreate, request: Request, user: User = Depends(require_permissions(P.DATASET_UPLOAD)), db: Session = Depends(get_db)):
    s = DataSource(**payload.model_dump())
    db.add(s)
    db.flush()
    audit.record(db, "dataset.source_create", user=user, resource_type="data_source", resource_id=s.id, request=request)
    db.commit()
    return DataSourceOut.model_validate(s)


@router.post("", response_model=DatasetDetail, status_code=status.HTTP_201_CREATED)
def create_dataset(payload: DatasetCreate, request: Request, user: User = Depends(require_permissions(P.DATASET_UPLOAD)), db: Session = Depends(get_db)):
    ds = svc.create_dataset(db, payload, user, request)
    return _detail(db, ds)


def _detail(db: Session, ds) -> DatasetDetail:
    out = DatasetDetail.model_validate(ds)
    out.versions = [DatasetVersionOut.model_validate(v) for v in ds.versions]
    out.source = DataSourceOut.model_validate(ds.source) if ds.source else None
    if ds.current_version_id:
        out.observation_count = db.scalar(select(func.count(Observation.id)).where(Observation.dataset_version_id == ds.current_version_id)) or 0
    return out


@router.get("/{ds_id}", response_model=DatasetDetail)
def get_dataset(ds_id: uuid.UUID, request: Request, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    return _detail(db, svc.get_dataset(db, ds_id, user, _perms_for(request, user, db)))


@router.patch("/{ds_id}", response_model=DatasetOut)
def update_dataset(ds_id: uuid.UUID, payload: DatasetUpdate, request: Request, user: User = Depends(require_permissions(P.DATASET_UPDATE, P.DATASET_UPLOAD, any_of=True)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ds = svc.get_dataset(db, ds_id, user, perms)
    return DatasetOut.model_validate(svc.update_dataset(db, ds, payload, user, perms, request))


@router.post("/{ds_id}/versions", response_model=DatasetVersionOut, status_code=status.HTTP_201_CREATED)
async def upload_version(ds_id: uuid.UUID, request: Request, file: UploadFile = File(...), change_note: Optional[str] = Form(None), version_label: Optional[str] = Form(None), user: User = Depends(require_permissions(P.DATASET_UPLOAD)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    ds = svc.get_dataset(db, ds_id, user, perms)
    data = read_upload(file.file, settings.max_upload_mb)
    return DatasetVersionOut.model_validate(svc.upload_version(db, ds, data=data, filename=file.filename or "upload", declared_mime=file.content_type, user=user, perms=perms, change_note=change_note, version_label=version_label, request=request))


@router.get("/{ds_id}/observations", response_model=Page[ObservationOut])
def observations(ds_id: uuid.UUID, request: Request, page: PageParams = Depends(), variable_code: Optional[str] = None, admin_unit_id: Optional[uuid.UUID] = None, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    ds = svc.get_dataset(db, ds_id, user, _perms_for(request, user, db))
    rows, total = svc.observations(db, ds, variable_code=variable_code, admin_unit_id=admin_unit_id, offset=page.offset, limit=page.page_size)
    return Page.build([ObservationOut.model_validate(r, from_attributes=True) for r in rows], total, page.page, page.page_size)


@router.get("/{ds_id}/download")
def download(ds_id: uuid.UUID, request: Request, version_id: Optional[uuid.UUID] = None, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    ds = svc.get_dataset(db, ds_id, user, _perms_for(request, user, db))
    vid = version_id or ds.current_version_id
    v = db.get(DatasetVersion, vid) if vid else None
    if not v or v.dataset_id != ds.id or not v.storage_key:
        raise NotFoundError("No file for this dataset")
    ds.download_count = (ds.download_count or 0) + 1
    audit.record(db, "dataset.download", user=user, resource_type="dataset", resource_id=ds.id, detail={"version": v.version_number}, request=request)
    db.commit()
    return StreamingResponse(get_storage().stream(v.storage_key), media_type=v.mime_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{v.file_name}"', "X-Checksum-SHA256": v.checksum_sha256 or ""})


@router.post("/{ds_id}/submit", response_model=DatasetOut)
def submit(ds_id: uuid.UUID, request: Request, user: User = Depends(require_permissions(P.DATASET_UPLOAD)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    return DatasetOut.model_validate(svc.submit(db, svc.get_dataset(db, ds_id, user, perms), user, perms, request))


@router.post("/{ds_id}/approve", response_model=DatasetOut)
def approve(ds_id: uuid.UUID, payload: ApprovalDecision, request: Request, user: User = Depends(require_permissions(P.DATASET_APPROVE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    return DatasetOut.model_validate(svc.approve(db, svc.get_dataset(db, ds_id, user, perms), user, payload.decision, payload.note, request))


@router.post("/{ds_id}/publish", response_model=DatasetOut)
def publish(ds_id: uuid.UUID, request: Request, access_level: Annotated[Optional[str], Query(pattern="^(public|open|internal|restricted)$")] = None, user: User = Depends(require_permissions(P.DATASET_APPROVE)), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    return DatasetOut.model_validate(svc.publish(db, svc.get_dataset(db, ds_id, user, perms), user, access_level, request))


@router.post("/{ds_id}/archive", response_model=DatasetOut)
def archive(ds_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), perms=Depends(get_permissions), db: Session = Depends(get_db)):
    return DatasetOut.model_validate(svc.archive(db, svc.get_dataset(db, ds_id, user, perms), user, perms, request))
