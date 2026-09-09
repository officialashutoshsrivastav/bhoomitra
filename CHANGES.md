# Bhoomitra — complete project

This is your full project with the backend fix and the frontend redesign already
applied. Nothing to merge: extract it and use it as your project folder.

`node_modules`, `.next` and `__pycache__` are not included — they are generated.

## Run it

```bash
docker compose up -d --build
docker compose exec backend python scripts/seed.py
```

`--build` matters. `docker compose down && up` alone reuses the old image, since
`frontend.Dockerfile` copies the source in at build time and there is no bind
mount for the frontend service.

Frontend on http://localhost:3000, API on http://localhost:8000, docs on
http://localhost:8000/docs.

### Faster loop while working on the UI

Rebuilding the image for every CSS change is slow. Either run the frontend on
the host:

```bash
cd frontend && npm install && npm run dev
```

or add a `docker-compose.override.yml` at the project root, which Compose picks
up automatically:

```yaml
services:
  frontend:
    build:
      context: .
      dockerfile: infrastructure/docker/frontend.Dockerfile
      target: deps
    working_dir: /app
    command: npm run dev
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
```

---

## What changed

### Backend — one bug

`/docs`, `/redoc` and `/openapi.json` returned 500. Every other endpoint worked;
the app imported fine with all 200 routes.

Every router uses `from __future__ import annotations` (PEP 563), which turns
annotations into strings. Combined with the old parameter style —

```python
q: Optional[str] = Query(None, max_length=120)
```

— FastAPI is left holding `Annotated[ForwardRef('Optional[str]'), Query(None)]`,
cannot resolve it, and the whole OpenAPI document fails with
`PydanticUserError`. It reproduces on the pinned `fastapi==0.115.6` and
`pydantic==2.10.4`.

55 parameters across 13 routers now use the `Annotated` form FastAPI
recommends, which resolves correctly under PEP 563:

```python
q: Annotated[Optional[str], Query(max_length=120)] = None
```

`app/schemas/common.py` also drops its `from __future__ import annotations`,
because FastAPI does not resolve forward references for a dependency class's
`__init__` and `PageParams` needs real annotation objects.

Nothing else in the backend was reviewed — this was a quick pass, not an audit.

### Frontend

Inter was named in `tailwind.config.ts` but never actually loaded, so every page
was silently falling back to the system UI font. Fonts are now linked in the
document head rather than fetched by `next/font`, so `next build` also works on
a machine with no route to Google.

New files:

| File | Purpose |
|---|---|
| `frontend/src/lib/motion.ts` | Hooks — reduced motion, in-view, count-up, scroll, sequence |
| `frontend/src/components/motion.tsx` | Reveal, Stagger, Counter, Ripple, Collapse, Skeleton, rails |
| `frontend/src/components/Loader.tsx` | Logo loader — boot screen, route progress, panel loader |
| `frontend/public/hero-valley.png` | Your photo, right edge cropped to drop the green streak |
| `frontend/public/hero-india.png` | Your India map, white background knocked out |
| `frontend/public/banner-strip.png` | Your banner |

Rewritten: `globals.css`, `tailwind.config.ts`, `layout.tsx`, `ui.tsx`,
`AppShell.tsx`, `site.tsx`, `catalogue.tsx`, `(site)/page.tsx`, `app/page.tsx`.

No new npm dependencies were added.

`ui.tsx` is imported by 38 of the 43 pages and every signature is unchanged, so
the pages that were not individually rewritten still pick up the new design
through it.

---

## Verified

- Backend: 107 files compile, app imports with 200 routes, OpenAPI generates
  161 paths and 109 schemas
- Frontend: `tsc --noEmit` clean under strict mode, `next build` across all 43
  routes, `next lint` clean, shared JS unchanged at 87.9 kB
- Rendered and checked at 1440px and 390px

## Not verified

`backend/tests/` needs a live PostgreSQL with PostGIS and pgvector, which was
not available here. Run them yourself:

```bash
docker compose up -d postgis
cd backend && pytest
```

## Still original

`LandMap.tsx` and the internals of the remaining 40 page bodies. They inherit
the new design through the shared components, but their own layouts were not
reworked.
