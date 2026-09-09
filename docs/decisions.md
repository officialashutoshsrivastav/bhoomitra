# Architecture decision records

### ADR-1 — Ministry attribution: DoLR, not MoSPI
The written brief places the platform under the **Department of Land Resources, Ministry of Rural
Development (PME Division)**, while the supplied visual mockups carry a *Ministry of Statistics &
Programme Implementation* footer. The brief is authoritative, so all copy, the footer and the About
page name DoLR/MoRD; the mockup text is treated as illustrative branding. Changing it later is a
content edit in `components/site.tsx` and the About page.

### ADR-2 — Statistics on screen are computed, never hard-coded
The mockups show figures such as “1,280+ publications”. Presenting invented numbers in a government
platform is unacceptable, so every counter is computed from the database via
`/dashboards/public-overview` and friends. When the underlying rows are seeded demo records the
counter is badged **Demo / Synthetic**.

### ADR-3 — Demo data is generated, labelled and reversible
A demonstration needs content, but fabricated content must never look official. The seeder creates
synthetic documents, statistics, boundaries, scenarios and challenges, each carrying `is_demo=true`
and a “DEMO / SYNTHETIC DATA” header inside document text. Seeding is idempotent (guarded by a
`demo.seeded_at` system setting) and can be disabled with `DEMO_DATA_ENABLED=false`.

### ADR-4 — Synthetic boundaries until geoBoundaries is loaded
Bundling national boundary files would ship licensed data of uncertain provenance and bloat the
repository. Instead the seeder builds six synthetic “Demo State” cells with 24 districts, and
`scripts/load_boundaries.py` / Administration → Integrations loads real geoBoundaries (CC BY 4.0)
when the deployment has internet access.

### ADR-5 — Citation-only extractive answering as the default
Without an LLM key the assistant still works: it retrieves passages and answers by quoting them with
numbered citations. This makes the platform demonstrable offline and, more importantly, makes the
no-hallucination guarantee structural rather than prompt-dependent. Setting `AI_PROVIDER=openai`
swaps in generative synthesis that is still constrained to the retrieved passages.

### ADR-6 — Every optional dependency has an in-process fallback
OpenSearch → PostgreSQL full-text; S3/MinIO → local disk; Celery/Redis → thread pool (or inline in
tests); hosted embeddings → deterministic hashing embeddings; STAC → demo scene adapter. The
platform therefore runs on a single machine with only PostgreSQL, and each connector reports whether
it is `live` or `demo` in Administration → Integrations.

### ADR-7 — Five value kinds on every number
Mixing measured, modelled and assumed values is how decision-support tools mislead. Observations,
indicators, analytics outputs, remote-sensing products and simulation results all carry one of
OBSERVED / MODELLED / ASSUMPTION / SCENARIO / UNCERTAINTY, and the UI renders it as a badge next to
the number.

### ADR-8 — The simulation engine is transparent, not predictive
The land-use model is a documented system of coefficients with declared ranges, run through Monte
Carlo sampling to produce p10–p90 bands. Its model card lists every coefficient, its basis and its
limitations, and each scenario stores 30+ explicit assumptions. It is a reasoning aid for comparing
interventions, not a forecast.

### ADR-9 — The prototype folder was folded into the backend
The uploaded prototype was a near-empty scaffold. Rather than preserve its structure, its intent was
absorbed into `backend/app` with a conventional FastAPI layout (api / services / models / schemas),
so there is a single coherent codebase.

### ADR-10 — Tests run against a real PostGIS database
Spatial predicates, geodesic areas and vector similarity cannot be exercised meaningfully against
SQLite or mocks. The suite therefore recreates the schema with the real migrations
(`downgrade base` → `upgrade head`) and runs 63 tests against PostgreSQL + PostGIS + pgvector, which
also verifies that the migrations themselves are reversible.
