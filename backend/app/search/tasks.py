from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.platform import BackgroundJob
from app.search.indexer import reindex_all
from app.workers.dispatch import register_job


@register_job("search.reindex")
def _job_reindex(db: Session, job: BackgroundJob) -> Dict[str, Any]:
    counts = reindex_all(db)
    return {"indexed": counts, "opensearch": any(counts.values())}
