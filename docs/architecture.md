# Architecture

## Overview

Bhoomitra is a three-tier application: a Next.js 14 browser client, a FastAPI service layer, and a
PostgreSQL 16 database with PostGIS (geometry) and pgvector (embeddings). Long-running work
(document extraction, OCR, embedding, report generation) is dispatched to background workers.
Everything that produces a decision-support output also writes to a shared **evidence engine**, so
any answer, statistic, map result or projection can be traced back to its sources.

```
Browser ── Next.js (SSR + client) ──/api rewrite──▶ FastAPI ──▶ PostgreSQL 16
                                                      │            ├── PostGIS  (admin units, layers, features)
                                                      │            └── pgvector (chunk embeddings)
                                                      ├──▶ Redis + Celery      (async jobs)
                                                      ├──▶ OpenSearch          (optional keyword index)
                                                      ├──▶ S3 / MinIO          (optional object storage)
                                                      └──▶ STAC / geoBoundaries / data.gov.in / LLM API
```

Every external dependency is optional and has an in-process fallback, so the platform runs on a
single machine with just PostgreSQL: PostgreSQL full-text instead of OpenSearch, local disk instead
of S3, a thread pool instead of Celery, deterministic hashing embeddings instead of a hosted model,
and a citation-only extractive answerer instead of an LLM.

## Backend module map (`backend/app`)

| Package | Responsibility |
| --- | --- |
| `core/` | Settings, logging, security primitives, permissions catalogue, middleware, exceptions |
| `db/` | Engine, session factory, base model |
| `models/` | SQLAlchemy models: identity, knowledge, datasets, gis, intelligence, platform |
| `schemas/` | Pydantic request/response contracts |
| `api/v1/` | Routers: auth, documents, research/policies, datasets, search/ai/evidence, gis, analytics, simulations, workspaces, innovation, dashboards, reports, integrations, notifications, users/organisations, admin/audit |
| `services/` | Domain services (auth, documents, datasets) — workflow, permissions, audit |
| `ingestion/` | Upload validation → extraction → OCR → chunking → embedding → indexing pipeline |
| `search/` | Keyword backend, vector backend, reciprocal-rank fusion, indexer |
| `ai/` | Embedding providers, retrieval, answerers, conversation handling |
| `gis/` | PostGIS service, spatial operations, remote sensing products |
| `analytics/` | Statistical procedures and the model registry |
| `simulation/` | Land-use scenario engine, Monte Carlo, indicator series |
| `integrations/` | geoBoundaries, data.gov.in, STAC, OpenSearch, storage, LLM, email connectors |
| `storage/` | Local and S3 backends, MIME sniffing, malware-scan hook |
| `workers/` | Celery app, task dispatch, thread/inline execution modes |
| `reporting/` | PDF (ReportLab), CSV, XLSX (openpyxl) renderers |
| `notifications/` | In-app notifications and email dispatch |
| `audit/` | Append-only audit log |
| `seed/` | Bootstrap (roles, permissions, admin) and Demo / Synthetic Data |

## Request flow

1. Middleware assigns a request ID, applies security headers and rate limits, and logs the request.
2. `deps.py` resolves the bearer token → user → permission set (rejecting tokens invalidated by a
   password change via the `pv` claim).
3. The route checks permissions declaratively (`require_permissions(P.DOCUMENT_CREATE)`).
4. Services enforce ownership/visibility rules, mutate state, write an audit record, and commit.
5. Errors are converted into a uniform envelope: `{"error": {code, message, details, request_id}}`.

## Document processing pipeline

```
upload → checksum + MIME sniff + malware hook → store blob → create version (UPLOADED)
      → VALIDATING → PROCESSING (text extraction: PDF/DOCX/TXT/CSV/XLSX/image)
      → OCR_RUNNING (only if a page has no text layer and Tesseract is available)
      → chunking (paragraph-aware, de-duplicated) → embedding (pgvector) 
      → INDEXING (keyword index) → READY
```

The version row records `processing_status`, `processing_error`, page/chunk counts and the embedding
model; a `Job` row records progress and retries. The frontend polls
`/documents/{id}/versions/{vid}/status` and shows the stage bar.

## Evidence engine

Every AI answer, analytics run, spatial operation, remote-sensing product and simulation run creates
a `Recommendation` with ranked `Evidence` items and provenance edges. `/evidence/{id}` explains the
output in steps; `/evidence/{id}/trace` returns a node/edge graph (recommendation → evidence →
chunk → version → document, or scenario → run → model version → assumptions). Values everywhere
carry one of five labels: **OBSERVED, MODELLED, ASSUMPTION, SCENARIO, UNCERTAINTY**.

## Frontend structure (`frontend/src`)

* `app/(site)/` — public pages (home, about, features, research, datasets, documents, policy, map,
  innovation, search, login/signup, legal, contact).
* `app/app/` — authenticated console behind `AppShell` (auth guard + role-aware sidebar): dashboard,
  repository, datasets, search, AI, evidence, GIS, analytics, simulation, workspaces, innovation,
  reports, notifications, profile, administration.
* `lib/api.ts` — fetch wrapper: in-memory access token, HttpOnly-cookie refresh with single-flight
  retry on 401.
* `lib/auth.tsx` — session context exposing `can()` / `hasRole()` so the UI mirrors server permissions.
* `components/` — UI primitives, catalogue widgets, MapLibre map, app shell.
