# Bhoomitra — Land Governance Intelligence Platform

A national digital platform for research, policy innovation and evidence-based land governance,
built for the **Policy, Monitoring & Evaluation (PME) Division, Department of Land Resources,
Ministry of Rural Development, Government of India**.

It brings documents, datasets, maps, models and people into one accountable system: a versioned
research repository, a dataset catalogue, hybrid search, an evidence-based AI assistant, PostGIS
geospatial analysis, remote sensing, an analytics engine, a policy simulation lab, collaborative
workspaces and an innovation portal — all behind a 13-role permission model with an append-only
audit trail.

> **Demo / Synthetic Data.** A fresh install seeds clearly-labelled synthetic documents, statistics,
> boundaries and challenges so every screen has something to show. They are badged
> *Demo / Synthetic* everywhere and flagged `is_demo: true` in the API. They are **not** official
> statistics and must never be quoted as such. Set `DEMO_DATA_ENABLED=false` to skip seeding.

---

## Contents

```
bhoomitra/
├── backend/            FastAPI + SQLAlchemy + PostGIS + pgvector
│   ├── app/            application code (api, services, ai, gis, analytics, simulation …)
│   ├── alembic/        database migrations
│   ├── scripts/        seed.py, create_superuser.py, load_boundaries.py
│   ├── tests/          63 pytest tests against a real PostGIS database
│   └── requirements.txt
├── frontend/           Next.js 14 (App Router) + TypeScript + Tailwind + MapLibre
├── database/init/      PostgreSQL extension bootstrap (postgis, vector, pg_trgm …)
├── infrastructure/     Dockerfiles
├── docs/               architecture, api, database, ai, gis, security, deployment, decisions
├── docker-compose.yml  full local stack (db, redis, opensearch, minio, api, worker, web)
└── Makefile            shortcuts for the commands below
```

---

## Option A — Run with Docker (easiest)

Requires Docker with the Compose plugin.

```bash
cd bhoomitra
docker compose up -d --build          # starts postgis, redis, opensearch, minio, backend, worker, frontend
docker compose exec backend python scripts/seed.py    # creates roles, admin and demo data
```

The database image is built from `infrastructure/docker/postgis.Dockerfile`, which adds **pgvector**
on top of PostGIS — both extensions are required. PostgreSQL is published on host port **5433** so it
does not clash with a PostgreSQL you may already run locally; inside the compose network the backend
still talks to `postgis:5432`.

If a port is already taken on your machine, change only the number on the **left** of the colon in
`docker-compose.yml` (e.g. `"3001:3000"`). If a start-up fails, `docker compose logs backend --tail 60`
shows why; after fixing a database problem run `docker compose down -v` so the volume is recreated and
the extension bootstrap runs again.

If seeding ever reports a missing table, the migration did not complete — run it by hand and read the
error it prints:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current      # should print "0002 (head)"
docker compose exec backend python scripts/seed.py
```

Open:

| What | URL |
| --- | --- |
| Web application | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health/ready |

Stop with `docker compose down` (add `-v` to also delete the database volume).

For production use the overlay, which turns off debug and demo data and requires real secrets:

```bash
JWT_SECRET_KEY=... DATABASE_URL=... CORS_ORIGINS=https://your.domain \
BOOTSTRAP_SUPERADMIN_EMAIL=... BOOTSTRAP_SUPERADMIN_PASSWORD=... \
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Option B — Run locally without Docker

### 1. Prerequisites

* **PostgreSQL 16** with **PostGIS 3.4** and **pgvector** extensions
* **Python 3.12**
* **Node.js 20+** (22 recommended)
* Optional: Redis (only if you want Celery workers), Tesseract + Poppler (only for OCR of scanned PDFs)

### 2. Database

```bash
sudo -u postgres psql <<'SQL'
CREATE USER bhoomitra WITH PASSWORD 'bhoomitra_dev_password';
CREATE DATABASE bhoomitra OWNER bhoomitra;
CREATE DATABASE bhoomitra_test OWNER bhoomitra;
SQL

for db in bhoomitra bhoomitra_test; do
  sudo -u postgres psql -d $db -c "CREATE EXTENSION IF NOT EXISTS postgis;
                                   CREATE EXTENSION IF NOT EXISTS vector;
                                   CREATE EXTENSION IF NOT EXISTS pg_trgm;
                                   CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
done
```

### 3. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # edit DATABASE_URL and JWT_SECRET_KEY
alembic upgrade head          # create the schema
python scripts/seed.py        # roles, permissions, super admin, demo data

uvicorn app.main:app --reload --port 8000
```

The API is now on **http://localhost:8000** (`/docs` for Swagger, `/redoc` for ReDoc).

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # API_INTERNAL_URL=http://localhost:8000 is the default
npm run dev
```

Open **http://localhost:3000**.

---

## Logging in

`scripts/seed.py` creates the super administrator from your `.env`:

| Role | Email | Password |
| --- | --- | --- |
| Super administrator | `admin@bhoomitra.in` | `Admin@Bhoomitra2026` |

…and, when `DEMO_DATA_ENABLED=true`, one demo account per role — all with the password
**`Demo@Bhoomitra2026`**:

| Role | Email |
| --- | --- |
| Platform administrator | `platform.admin@demo.bhoomitra.in` |
| Government official | `official@demo.bhoomitra.in` |
| Policy maker | `policy.maker@demo.bhoomitra.in` |
| Researcher | `researcher@demo.bhoomitra.in` |
| Academic | `academic@demo.bhoomitra.in` |
| Research organisation | `research.org@demo.bhoomitra.in` |
| GIS analyst | `gis.analyst@demo.bhoomitra.in` |
| Data analyst | `data.analyst@demo.bhoomitra.in` |
| Project manager | `project.manager@demo.bhoomitra.in` |
| Innovation evaluator | `evaluator@demo.bhoomitra.in` |
| Expert / industry | `expert@demo.bhoomitra.in` |
| Public user | `public@demo.bhoomitra.in` |

**Change every one of these before any real deployment.** Create your own administrator with:

```bash
python scripts/create_superuser.py --email you@dept.gov.in --name "Your Name" --password 'Str0ng&Passw0rd'
```

---

## A five-minute tour

1. **Home / Research / Datasets / Policy / Map** — public pages, no login needed.
2. Sign in as `policy.maker@demo.bhoomitra.in` → **Dashboard** shows role-specific widgets.
3. **AI Assistant** → ask *“By how much did drone resurvey reduce boundary disputes?”* — you get a
   cited answer, a confidence score and a **Evidence trace** link showing the full provenance graph.
   Ask something outside the corpus (*“What is the population of Mars?”*) and it refuses.
4. **GIS Workbench** → pick a layer and a district, run *Aggregate*, *Hotspot* or *Affected area*;
   switch to **Remote sensing** to search scenes and compute NDVI / change detection.
5. **Simulation Lab** → open *Afforest 120 km² of wasteland*, press **Run**, inspect the indicator
   bands (p10–p90), risk flags and the 30+ explicit assumptions; then **Compare runs**.
6. **Analytics** → run a *Forecast* on “District Cropping Intensity” and see the MODELLED band.
7. Sign in as `official@demo.bhoomitra.in` → **Repository** → *Awaiting review* to approve/publish.
8. Sign in as `admin@bhoomitra.in` → **Administration** for users, roles, approvals, integrations,
   jobs, settings and the audit log.

---

## Tests

```bash
cd backend && python -m pytest          # 63 tests; runs the migrations then hits a real PostGIS db
cd frontend && npx tsc --noEmit         # type check
cd frontend && npm run build            # production build
```

The test suite needs `TEST_DATABASE_URL` (defaults to the local `bhoomitra_test` database) and
recreates the schema on every run via `alembic downgrade base && alembic upgrade head`.

---

## Loading real data

* **Boundaries** — replace the synthetic demo cells with real administrative boundaries from
  geoBoundaries (CC BY 4.0):
  `python scripts/load_boundaries.py --adm ADM1 --adm ADM2 --iso3 IND` (needs internet access), or
  use Administration → Integrations → *Load ADM1*.
* **Statistics** — register a dataset in the catalogue and upload a CSV/XLSX. Rows shaped
  `variable, district (or admin_code), year, value, unit` are ingested as observations and linked to
  administrative units automatically.
* **Documents** — Repository → *New document*, upload a PDF/DOCX/TXT; extraction, OCR, chunking,
  embedding and indexing run in the background.
* **Generative AI** — set `AI_PROVIDER=openai` and `OPENAI_API_KEY`; without a key the assistant runs
  in citation-only extractive mode (it quotes retrieved passages and never invents text).
* **Scale-out search / storage** — set `OPENSEARCH_URL` and `STORAGE_BACKEND=s3` to move off the
  PostgreSQL full-text fallback and local disk.

---

## Documentation

| File | Contents |
| --- | --- |
| `docs/architecture.md` | System design, modules, request and processing flows |
| `docs/api.md` | REST conventions, auth, error format, endpoint map |
| `docs/database.md` | Schema, tables, indexes, migrations |
| `docs/ai.md` | Retrieval, RAG pipeline, evidence engine, value-kind labels |
| `docs/gis.md` | Spatial model, operations, remote sensing |
| `docs/security.md` | Authentication, RBAC, uploads, audit, hardening checklist |
| `docs/deployment.md` | Environments, scaling, backups, operations |
| `docs/decisions.md` | Architecture decision records, including known deviations |

---

© 2026 Bhoomitra · Department of Land Resources, Ministry of Rural Development.
Decision-support outputs are not official government decisions or statistics.
