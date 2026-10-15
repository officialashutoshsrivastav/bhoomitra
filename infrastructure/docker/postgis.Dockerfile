# PostgreSQL 16 with BOTH PostGIS (geometry) and pgvector (embeddings).
# The official postgis image does not ship pgvector, so we add it from the PGDG repo.
FROM postgis/postgis:16-3.4

RUN sed -i 's|deb.debian.org/debian-security|deb.debian.org/debian-security|g' /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
