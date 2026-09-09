from __future__ import annotations

from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.audit import service as audit
from app.core.permissions import P
from app.db.database import get_db
from app.integrations import service as integrations
from app.models.identity import User

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationUpdate(BaseModel):
    enabled: bool = True
    config: Optional[Dict[str, Any]] = None


@router.get("")
def list_integrations(user: User = Depends(require_permissions(P.INTEGRATION_MANAGE)), db: Session = Depends(get_db)):
    return {"items": integrations.list_all(db)}


@router.post("/{connector}/check")
def check(connector: str, user: User = Depends(require_permissions(P.INTEGRATION_MANAGE)), db: Session = Depends(get_db)):
    return integrations.check(db, connector)


@router.patch("/{connector}")
def update(connector: str, payload: IntegrationUpdate, request: Request, user: User = Depends(require_permissions(P.INTEGRATION_MANAGE)), db: Session = Depends(get_db)):
    out = integrations.set_enabled(db, connector, payload.enabled, payload.config)
    audit.record(db, "integration.update", user=user, resource_type="integration", detail={"connector": connector, "enabled": payload.enabled}, request=request, commit=True)
    return out


@router.post("/geoboundaries/load")
def load_boundaries(request: Request, iso3: Annotated[str, Query(max_length=3)] = "IND", adm: Annotated[str, Query(pattern="^(ADM0|ADM1|ADM2)$")] = "ADM1", replace: bool = False, user: User = Depends(require_permissions(P.INTEGRATION_MANAGE)), db: Session = Depends(get_db)):
    out = integrations.load_geoboundaries(db, iso3.upper(), adm, replace)
    audit.record(db, "integration.geoboundaries_load", user=user, resource_type="admin_unit", detail=out, request=request, commit=True)
    return out
