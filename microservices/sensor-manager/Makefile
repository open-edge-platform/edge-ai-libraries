# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL := /bin/bash

COMPOSE_FILE := docker/compose.yaml
COMPOSE := docker compose --env-file .env -f $(COMPOSE_FILE)

UV_VERSION := 0.9.10
LOCAL_UV := .tools/uv/bin/uv
UV := $(or $(shell command -v uv 2>/dev/null),$(LOCAL_UV))

.PHONY: help env build run stop logs install test coverage lint format clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

# Fallback for environments without uv (e.g. CI runners).
$(LOCAL_UV):
	python3 -m venv .tools/uv
	.tools/uv/bin/pip install --quiet uv==$(UV_VERSION)

.env:
	cp .env.example .env

env: .env ## Create .env from .env.example if missing

build: .env ## Build the Docker image
	$(COMPOSE) build

run: .env ## Start the service in the background
	$(COMPOSE) up -d

stop: .env ## Stop the service
	$(COMPOSE) down

logs: .env ## Follow service logs
	$(COMPOSE) logs -f

install: $(if $(filter $(LOCAL_UV),$(UV)),$(LOCAL_UV)) ## Install Python dependencies (including dev extras) with uv
	$(UV) sync --frozen --extra dev

test: install ## Run unit tests
	$(UV) run pytest

coverage: install ## Run unit tests with coverage report
	$(UV) run pytest --cov=src --cov-branch --cov-report=term-missing --cov-report=html:coverage

lint: install ## Run ruff linter and format check
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

format: install ## Format code with ruff
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

clean: ## Remove caches and coverage artifacts
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage coverage htmlcov .tools
