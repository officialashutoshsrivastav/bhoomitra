.PHONY: help install migrate seed api worker web test lint docker-up docker-down
help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sed 's/^/make /'
install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install
migrate:
	cd backend && alembic upgrade head
seed:
	cd backend && python scripts/seed.py
api:
	cd backend && uvicorn app.main:app --reload --port 8000
worker:
	cd backend && celery -A app.workers.celery_app worker -l info
web:
	cd frontend && npm run dev
test:
	cd backend && python -m pytest
	cd frontend && npx tsc --noEmit
docker-up:
	docker compose up -d --build
docker-down:
	docker compose down
