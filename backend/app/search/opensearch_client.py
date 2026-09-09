from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("bhoomitra.opensearch")

_client = None
_client_failed = False

INDEX_MAPPINGS: Dict[str, Any] = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}, "analysis": {"analyzer": {"bm_text": {"type": "standard", "stopwords": "_english_"}}}},
    "mappings": {
        "properties": {
            "entity_type": {"type": "keyword"},
            "entity_id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "bm_text", "fields": {"raw": {"type": "keyword"}, "suggest": {"type": "completion"}}},
            "body": {"type": "text", "analyzer": "bm_text"},
            "keywords": {"type": "keyword"},
            "topic": {"type": "keyword"},
            "policy_area": {"type": "keyword"},
            "research_area": {"type": "keyword"},
            "document_type": {"type": "keyword"},
            "organization": {"type": "keyword"},
            "geography": {"type": "keyword"},
            "language": {"type": "keyword"},
            "source": {"type": "keyword"},
            "status": {"type": "keyword"},
            "visibility": {"type": "keyword"},
            "published_at": {"type": "date"},
            "is_demo": {"type": "boolean"},
            "updated_at": {"type": "date"},
        }
    },
}


def index_name() -> str:
    return f"{settings.opensearch_index_prefix}-content"


def get_client():
    global _client, _client_failed
    if not settings.opensearch_url or _client_failed:
        return None
    if _client is None:
        try:
            from opensearchpy import OpenSearch

            auth = (settings.opensearch_user, settings.opensearch_password) if settings.opensearch_user else None
            _client = OpenSearch(hosts=[settings.opensearch_url], http_auth=auth, verify_certs=settings.opensearch_verify_certs, ssl_show_warn=False, timeout=5)
            if not _client.indices.exists(index=index_name()):
                _client.indices.create(index=index_name(), body=INDEX_MAPPINGS)
        except Exception as exc:
            logger.warning("OpenSearch unavailable, falling back to PostgreSQL full-text search", extra={"extra_data": {"error": str(exc)[:200]}})
            _client = None
            _client_failed = True
    return _client


def opensearch_status() -> Dict[str, Any]:
    if not settings.opensearch_url:
        return {"ok": True, "configured": False, "mode": "postgres_fts", "note": "OpenSearch not configured; PostgreSQL full-text search in use"}
    client = get_client()
    if client is None:
        return {"ok": False, "configured": True, "mode": "postgres_fts", "error": "OpenSearch unreachable; PostgreSQL full-text search fallback active"}
    try:
        info = client.cluster.health()
        return {"ok": True, "configured": True, "mode": "opensearch", "cluster_status": info.get("status")}
    except Exception as exc:
        return {"ok": False, "configured": True, "mode": "postgres_fts", "error": str(exc)[:200]}


def index_document(doc: Dict[str, Any]) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        client.index(index=index_name(), id=f"{doc['entity_type']}:{doc['entity_id']}", body=doc, refresh=True)
        return True
    except Exception as exc:
        logger.warning("OpenSearch index failed", extra={"extra_data": {"error": str(exc)[:200]}})
        return False


def delete_document(entity_type: str, entity_id: str) -> bool:
    client = get_client()
    if client is None:
        return False
    try:
        client.delete(index=index_name(), id=f"{entity_type}:{entity_id}", ignore=[404], refresh=True)
        return True
    except Exception:
        return False


def keyword_search(query: str, filters: Dict[str, Any], size: int = 50) -> Optional[List[Dict[str, Any]]]:
    client = get_client()
    if client is None:
        return None
    must: List[Dict[str, Any]] = [{"multi_match": {"query": query, "fields": ["title^3", "keywords^2", "body"], "type": "best_fields", "fuzziness": "AUTO"}}] if query else [{"match_all": {}}]
    filter_clauses = [{"term": {k: v}} for k, v in filters.items() if v is not None and k not in {"date_from", "date_to"}]
    if filters.get("date_from") or filters.get("date_to"):
        rng: Dict[str, str] = {}
        if filters.get("date_from"):
            rng["gte"] = str(filters["date_from"])
        if filters.get("date_to"):
            rng["lte"] = str(filters["date_to"])
        filter_clauses.append({"range": {"published_at": rng}})
    body = {"size": size, "query": {"bool": {"must": must, "filter": filter_clauses}}, "highlight": {"fields": {"body": {"fragment_size": 160, "number_of_fragments": 1}}}}
    try:
        res = client.search(index=index_name(), body=body)
    except Exception as exc:
        logger.warning("OpenSearch query failed", extra={"extra_data": {"error": str(exc)[:200]}})
        return None
    out = []
    for hit in res.get("hits", {}).get("hits", []):
        src = hit["_source"]
        hl = hit.get("highlight", {}).get("body", [None])[0]
        out.append({"entity_type": src["entity_type"], "entity_id": src["entity_id"], "score": hit.get("_score", 0.0), "snippet": hl, "title": src.get("title")})
    return out


def suggest(prefix: str, size: int = 8) -> Optional[List[str]]:
    client = get_client()
    if client is None:
        return None
    try:
        res = client.search(index=index_name(), body={"suggest": {"s": {"prefix": prefix, "completion": {"field": "title.suggest", "size": size}}}, "_source": False})
        return [o["text"] for o in res["suggest"]["s"][0]["options"]]
    except Exception:
        return None
