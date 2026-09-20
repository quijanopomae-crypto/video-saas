PYTHON ?= python
NPM ?= npm

.PHONY: db-up db-down api web test ffmpeg-smoke

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

api:
	cd apps/api && $(PYTHON) -m uvicorn src.main:app --reload --port 8000

web:
	cd apps/web && $(NPM) run dev

test:
	$(PYTHON) -m pytest -q tests
	cd apps/api && $(PYTHON) -m pytest -q tests
	cd apps/web && $(NPM) test && $(NPM) run typecheck && $(NPM) run build

ffmpeg-smoke:
	cd apps/api && $(PYTHON) -m src.workers.render --smoke ../../artifacts/ffmpeg-smoke.mp4
