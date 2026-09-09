# PostgreSQL 16 with BOTH PostGIS (geometry) and pgvector (embeddings).
# The official postgis image does not ship pgvector, so we add it from the PGDG repo.
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
