PORT ?= 8765
UI_PORT ?= 5173
VENV := server/.venv
PY := $(VENV)/bin/python

.PHONY: help install install-server install-ui dev dev-server dev-ui build build-ui api-codegen run stop clean

help:
	@echo "make install       Install backend and frontend dependencies"
	@echo "make dev-server    Run the aggregation API on :$(PORT) with reload"
	@echo "make dev-ui        Run the Vite dev server on :$(UI_PORT)"
	@echo "make build         Build the UI into server/static"
	@echo "make api-codegen   Regenerate UI API types/hooks from the backend OpenAPI schema"
	@echo "make run           Build and run everything in Docker"
	@echo "make stop          Stop the Docker stack"

install: install-server install-ui

install-server:
	python3 -m venv $(VENV) || uv venv $(VENV)
	$(VENV)/bin/pip install -r server/requirements.txt

install-ui:
	cd ui && npm install

dev-server:
	cd server && ../$(VENV)/bin/python -m uvicorn app.main:app \
		--reload --host 0.0.0.0 --port $(PORT)

dev-ui:
	cd ui && npm run dev -- --port $(UI_PORT)

build build-ui:
	cd ui && npm run build

api-codegen:
	cd server && ../$(PY) -c \
		"import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" \
		> ../ui/openapi.json
	cd ui && npm run codegen

run:
	mkdir -p shared/db
	PORTAL_UID=$$(id -u) PORTAL_GID=$$(id -g) docker compose up --build -d

stop:
	docker compose down

clean:
	rm -rf server/static ui/dist ui/node_modules $(VENV) shared/db
