.PHONY: build up down test coverage coverage-html logs init-env clean

IMAGE_NAME   := alert-service
COMPOSE      := docker compose -f docker/docker-compose.yml

# Load .env if it exists
-include .env
export

## ── Build ──────────────────────────────────────────────
build:
ifeq ($(MQTT_MODE),embedded)
	$(COMPOSE) --profile embedded build
else
	$(COMPOSE) build
endif

## ── Service lifecycle ──────────────────────────────────
up:
ifeq ($(MQTT_MODE),embedded)
	@echo "Starting alert-service + embedded MQTT broker..."
	$(COMPOSE) --profile embedded up -d
else
	@echo "Starting alert-service (external MQTT: $(MQTT_HOST):$(MQTT_PORT))..."
	$(COMPOSE) up -d
endif

down:
ifeq ($(MQTT_MODE),embedded)
	$(COMPOSE) --profile embedded down
else
	$(COMPOSE) down
endif

logs:
	$(COMPOSE) logs -f alert-service

## ── Environment ────────────────────────────────────────
init-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env created from .env.example — edit it as needed"; \
	else \
		printf ".env already exists. Overwrite? [y/N] "; \
		read ans; \
		if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
			cp .env.example .env; \
			echo ".env overwritten from .env.example"; \
		else \
			echo "Skipped — existing .env kept"; \
		fi; \
	fi

## ── Tests ──────────────────────────────────────────────
VENV     := .venv
PIP      := $(VENV)/bin/pip
PYTEST   := $(VENV)/bin/pytest

$(VENV):
	python3 -m venv $(VENV)

test: $(VENV)
	$(PIP) install -q -r requirements.txt pytest pytest-asyncio pytest-cov httpx respx pytest-spec
	$(PYTEST) tests/ -v --tb=short

coverage: $(VENV)
	$(PIP) install -q -r requirements.txt pytest pytest-asyncio pytest-cov httpx respx pytest-spec coverage
	$(PYTEST) tests/ -v --tb=short --cov=src --cov-report=term-missing:skip-covered

coverage-html: coverage
	$(VENV)/bin/coverage html
	@echo "Coverage report: open htmlcov/index.html"

## ── Cleanup ────────────────────────────────────────────
clean:
	$(COMPOSE) down -v --rmi local
