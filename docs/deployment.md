# Deployment and operations

## Environments

| Variable | Development | Production |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `DEBUG` / `LOG_JSON` | `true` / `false` | `false` / `true` |
| `TASK_EXECUTION_MODE` | `thread` | `celery` (with Redis) |
| `STORAGE_BACKEND` | `local` | `s3` |
| `OPENSEARCH_URL` | empty (PostgreSQL FTS) | OpenSearch cluster |
| `AI_PROVIDER` | `local` | `openai` (optional) |
| `DEMO_DATA_ENABLED` | `true` | `false` |

## Docker

```bash
docker compose up -d --build                       # dev stack
docker compose exec backend python scripts/seed.py
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d   # prod overlay
```

The backend image runs `alembic upgrade head` on start. The frontend image builds Next.js in
standalone mode and serves it as a non-root user. Compose declares health checks so the API waits for
PostgreSQL and Redis.

## Manual deployment

1. Provision PostgreSQL 16 + PostGIS + pgvector; create the database and extensions.
2. `pip install -r backend/requirements.txt`; set the environment; `alembic upgrade head`;
   `python scripts/seed.py --no-demo`; `python scripts/create_superuser.py ...`.
3. Run the API under a process manager:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4` behind Nginx/Caddy with TLS.
4. Run at least one worker: `celery -A app.workers.celery_app worker -l info` (plus `beat` if you
   schedule periodic jobs).
5. `cd frontend && npm ci && npm run build && npm start` (or serve the standalone output), with
   `API_INTERNAL_URL` pointing at the API.

## Scaling notes

* The API is stateless — scale horizontally behind a load balancer; sessions live in the database.
* Ingestion and report generation are the CPU-heavy paths: scale workers, not API replicas.
* Move keyword search to OpenSearch once the corpus exceeds a few hundred thousand chunks.
* pgvector: raise `ivfflat.probes` for recall, and re-index after bulk loads or a provider change.
* Simplify geometry on read and consider vector tiles for very large layers.

## Backups and recovery

* Nightly `pg_dump` plus WAL archiving for point-in-time recovery; test restores quarterly.
* Object storage with versioning; blobs and database must be restored to the same point.
* Re-runnable recovery steps: `alembic upgrade head`, then
  Administration → Jobs → *Rebuild search index* to regenerate derived indexes.

## Monitoring

* `GET /health/live` (process) and `GET /health/ready` (database, storage, dependencies).
* Structured JSON logs with request IDs; every audit row carries the same request ID for correlation.
* Watch: failed jobs (`/admin/jobs`), versions stuck in processing, failed logins in 24h
  (`/admin/overview`), and connector status (`/integrations`).
