# API reference

Base URL: `/api/v1`. Interactive documentation: `/docs` (Swagger) and `/redoc`.

## Conventions

* JSON in, JSON out; UUID identifiers; ISO-8601 timestamps (UTC).
* Collections return `{"items": [...], "total": n, "page": 1, "page_size": 20, "pages": 3}`.
* Errors return `{"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}`
  with an appropriate status (400 validation, 401 auth, 403 permission, 404 not found, 409 conflict,
  422 domain validation, 429 rate limit).
* Every response carries `X-Request-ID`; downloads also carry `X-Checksum-SHA256`.

## Authentication

```http
POST /api/v1/auth/login      {"email": "...", "password": "..."}
  → {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}
```

Send `Authorization: Bearer <access_token>`. Refresh tokens rotate on every use and are also set as
an HttpOnly cookie; reusing a rotated token revokes the whole family (`token_reuse`).

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/register` | Self-registration (Public User role) |
| `POST /auth/activate` | Activate with emailed token |
| `POST /auth/refresh` | Rotate tokens |
| `POST /auth/logout` | Revoke the presented refresh token |
| `POST /auth/password/forgot` · `/reset` · `/change` | Password lifecycle |
| `GET`/`PATCH /auth/me` | Current user, roles, permissions |

## Endpoint map

| Area | Endpoints |
| --- | --- |
| Documents | `GET/POST /documents`, `GET/PATCH/DELETE /documents/{id}`, `/versions`, `/versions/{vid}/status`, `/versions/{vid}/retry`, `/versions/{vid}/set-current`, `/download`, `/chunks`, `/submit`, `/review`, `/publish`, `/archive`, `/relations`, `/pending-review` |
| Research & policy | `GET/POST /research-projects`, `GET/POST /policies`, `/policies/facets`, `/policies/{id}`, `/policies/indicators/series` |
| Datasets | `GET/POST /datasets`, `/facets`, `/sources`, `/{id}`, `/{id}/versions`, `/{id}/observations`, `/{id}/download`, `/submit`, `/approve`, `/publish`, `/archive`, `/pending-approval` |
| Search | `GET /search`, `/search/autocomplete`, `/search/facets`, `/search/recent`, `GET/POST/DELETE /search/saved` |
| AI | `POST /ai/ask`, `GET /ai/conversations[/{id}]`, `GET /ai/status` |
| Evidence | `GET /evidence/recommendations`, `/evidence/{id}`, `/evidence/{id}/trace`, `/evidence/node/{type}/{id}/trace` |
| GIS | `/gis/admin-units[/search|/geojson|/{id}]`, `/gis/layers[...]`, `/gis/layers/{id}/features|statistics|temporal|compare`, `/gis/ops/{intersection,area,proximity,aggregate,hotspot,boundary-select,affected-area}`, `/gis/ops/runs` |
| Remote sensing | `/remote-sensing/status`, `/scenes/search`, `/scenes/{id}`, `/scenes/{id}/products`, `/change` |
| Analytics | `GET /analytics/models`, `POST /analytics/run`, `GET /analytics/runs[/{id}]` |
| Simulation | `GET /simulations/model`, `GET/POST /simulations/scenarios`, `/{id}/run`, `/{id}/review`, `GET /simulations/runs/{id}`, `GET /simulations/compare?run_ids=`, `POST /simulations/baseline/from-layer` |
| Workspaces | `/workspaces` and nested `/members`, `/resources`, `/tasks`, `/comments`, `/activity`, `/transition` |
| Innovation | `/challenges[...]`, `/challenges/{id}/submissions`, `/submissions/{id}` + `/attachments`, `/submit`, `/evaluate`, `/decision`, `/pilots`, `/innovation/overview`, `/innovation/pilots` |
| Dashboards | `/dashboards/public-overview`, `/dashboards/me`, `/dashboards/national` |
| Reports | `GET /reports/types`, `POST /reports`, `GET /reports[/{id}]`, `/{id}/download` |
| Notifications | `GET /notifications`, `POST /notifications/read` |
| Users & orgs | `GET /users[/{id}]`, `GET/POST /organizations[...]` |
| Admin & audit | `/admin/users[...]`, `/admin/roles`, `/admin/approvals[/{id}/decide]`, `/admin/settings`, `/admin/jobs[/{id}/retry]`, `/admin/maintenance/reindex`, `/admin/overview`, `/audit`, `/audit/actions` |
| Integrations | `GET /integrations`, `POST /integrations/{connector}/check`, `PATCH /integrations/{connector}`, `POST /integrations/geoboundaries/load` |
| Health | `GET /health/live`, `GET /health/ready` (outside the `/api/v1` prefix) |

## Examples

```bash
# Ask the assistant
curl -s -X POST localhost:8000/api/v1/ai/ask -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"question":"By how much did drone resurvey reduce boundary disputes?"}'

# Aggregate a layer by district
curl -s -X POST localhost:8000/api/v1/gis/ops/aggregate -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"layer_id":"<uuid>","level":"district","metric":"area"}'

# Forecast a dataset variable
curl -s -X POST localhost:8000/api/v1/analytics/run -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"analysis_type":"forecast","dataset_version_id":"<uuid>","variable_code":"cropping_intensity","horizon":5}'
```
