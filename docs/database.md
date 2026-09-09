# Database

PostgreSQL 16 with **PostGIS 3.4** (geometry, geography, spatial indexes) and **pgvector**
(embedding similarity). `pg_trgm` powers autocomplete; `uuid-ossp` is available for identifiers.

## Table groups

| Group | Tables |
| --- | --- |
| Identity & access | `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `organizations`, `departments`, `refresh_tokens`, `password_reset_tokens`, `activation_tokens`, `login_attempts`, `system_settings` |
| Knowledge | `documents`, `document_versions`, `document_chunks`, `document_reviews`, `document_relations`, `policies`, `policy_indicators`, `research_projects`, `research_outputs` |
| Datasets | `data_sources`, `datasets`, `dataset_versions`, `dataset_variables`, `observations` |
| Geospatial | `admin_units`, `gis_layers`, `gis_features`, `spatial_runs`, `rs_scenes`, `rs_products` |
| Intelligence | `recommendations`, `evidence`, `provenance_edges`, `models`, `model_versions`, `analytics_runs`, `scenarios`, `scenario_assumptions`, `simulation_runs`, `simulation_results`, `conversations`, `ai_messages` |
| Platform | `workspaces`, `workspace_members`, `workspace_resources`, `tasks`, `comments`, `activities`, `challenges`, `submissions`, `submission_attachments`, `evaluations`, `pilots`, `notifications`, `reports`, `jobs`, `approvals`, `audit_logs`, `saved_searches`, `search_history`, `integration_states` |

## Notable design points

* **Soft deletes** — user-facing entities carry `deleted_at`; queries filter it out.
* **Versioning** — documents and datasets keep every uploaded version with `checksum_sha256`,
  `processing_status` and a pointer to the current version. Duplicate checksums are rejected (409).
* **Geometry** — `admin_units.geom` and `gis_features.geom` are `MULTIPOLYGON/GEOMETRY(SRID 4326)`
  with GiST indexes; areas are computed geodesically (`ST_Area(geography)`), never in degrees.
* **Embeddings** — `document_chunks.embedding vector(1536)` with an IVFFlat/cosine index; the
  dimension is fixed by `EMBEDDING_DIM` so providers can be swapped after a re-index.
* **Observations** — every numeric fact is one row (`variable_code`, `admin_unit_id`, `period_start`,
  `value`, `unit`, `value_kind`), which is what lets analytics, maps and simulations share data.
* **Append-only audit** — `audit_logs` has no update path; each row carries actor, action, resource,
  result, IP, user agent and request ID.
* **Value kinds** — `value_kind` columns on observations, indicators, simulation results and evidence
  record OBSERVED / MODELLED / ASSUMPTION / SCENARIO / UNCERTAINTY.

## Migrations

Alembic, in `backend/alembic/versions`:

* `0001_initial_schema.py` — extensions and the full schema.
* `0002_platform_extensions.py` — workspace/task/comment/activity and innovation columns.

```bash
alembic upgrade head          # apply
alembic downgrade base        # tear down (the test suite does this on every run)
alembic revision --autogenerate -m "message"
```

Downgrades are written to be reversible: nullable columns that become NOT NULL are back-filled first.
