# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Video Search & Summarization - Makefile
# ==============================================================================
#
# Build, test, and manage the Video Search & Summarization application.
# Supports code quality checks and security scanning for all components.
#
# Quick Start:
#   make help              - Show all available commands
#   make build             - Build all application Docker images
#   make test              - Run all unit tests
#   make trivy-scan        - Run all Trivy security scans
#
# ==============================================================================

SHELL := bash -eu -o pipefail
.DEFAULT_GOAL := help

# Auto-create .env from .env.example if it doesn't exist yet.
# This runs only for targets that actually require the env file.
$(if $(filter build build-deps push deploy-summary deploy-search deploy-dual deploy-unified health-check,$(MAKECMDGOALS)),$(shell [ -f .env ] || cp .env.example .env),)

# Load registry/tag defaults from .env at parse time so that `make build`
# and `make push` honour .env without requiring shell exports.
ifneq (,$(wildcard .env))
  _env_REGISTRY_URL := $(shell grep -m1 '^REGISTRY_URL=' .env 2>/dev/null | cut -d= -f2-)
  _env_PROJECT_NAME := $(shell grep -m1 '^PROJECT_NAME=' .env 2>/dev/null | cut -d= -f2-)
  _env_TAG          := $(shell grep -m1 '^TAG=' .env 2>/dev/null | cut -d= -f2-)
  ifneq (,$(_env_REGISTRY_URL))
    REGISTRY_URL ?= $(_env_REGISTRY_URL)
  endif
  ifneq (,$(_env_PROJECT_NAME))
    PROJECT_NAME ?= $(_env_PROJECT_NAME)
  endif
  ifneq (,$(_env_TAG))
    TAG ?= $(_env_TAG)
  endif
endif

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := vss
VERSION ?= latest
PYTHON_VERSION := ^3.11,<3.14
NODE_VERSION := 24
GO_VERSION := 1.23

# ==============================================================================
# Image Configuration
# ==============================================================================

# Set TAG to override the image tag (defaults to VERSION).
TAG ?= $(VERSION)

# Registry prefix can be supplied in two ways:
#   1. Set REGISTRY directly:         REGISTRY=myregistry.io/myproject/
#   2. Set REGISTRY_URL + PROJECT_NAME separately (trailing slashes are stripped):
#        REGISTRY_URL=myregistry.io  PROJECT_NAME=myproject
# If none are set, images are tagged without a registry prefix (local builds).
REGISTRY_URL ?=
PROJECT_NAME ?=
_REG_URL  := $(if $(REGISTRY_URL),$(patsubst %/,%,$(REGISTRY_URL))/)
_PRJ_NAME := $(if $(PROJECT_NAME),$(patsubst %/,%,$(PROJECT_NAME))/)
REGISTRY  ?= $(_REG_URL)$(_PRJ_NAME)

# ==============================================================================
# Component Configuration
# ==============================================================================

COMPONENTS := pipeline-manager vss-ui video-search video-ingestion
TEST_COMPONENTS := pipeline-manager vss-ui video-search video-ingestion

# Build contexts and Dockerfiles
pipeline-manager_CONTEXT_DIR := ./pipeline-manager
pipeline-manager_DOCKERFILE := ./pipeline-manager/Dockerfile
pipeline-manager_LANG := typescript

vss-ui_CONTEXT_DIR := ./ui/react
vss-ui_DOCKERFILE := ./ui/react/Dockerfile
vss-ui_LANG := typescript

video-search_CONTEXT_DIR := ./search-ms
video-search_DOCKERFILE := ./search-ms/docker/Dockerfile
video-search_LANG := python

video-ingestion_CONTEXT_DIR := ./video-ingestion
video-ingestion_DOCKERFILE := ./video-ingestion/docker/Dockerfile
video-ingestion_LANG := python

# Dependency microservices (built via build-deps, pulled from registry or official images via compose)
# vdms-dataprep, multimodal-embedding-serving, ovms-service, audio-analyzer
DEP_COMPONENTS := vdms-dataprep multimodal-embedding-serving

# Path to the sibling microservices directory (used by build-deps)
USERVICES_DIR := ../../microservices

# Build-dep source directories included in trivy-scan-fs
DEP_SCAN_DIRS := \
    $(USERVICES_DIR)/visual-data-preparation-for-retrieval \
    $(USERVICES_DIR)/multimodal-embedding-serving

# ==============================================================================
# Docker Build Arguments
# ==============================================================================
# Proxy args are included only when the corresponding environment variables are
# non-empty — empty or unset vars are silently omitted (never passed as "").
# Set ADD_COPYLEFT_SOURCES=true to inject COPYLEFT_SOURCES=true into every build.
DOCKER_BUILD_ARGS := \
  $(if $(http_proxy),--build-arg http_proxy=$(http_proxy)) \
  $(if $(https_proxy),--build-arg https_proxy=$(https_proxy)) \
  $(if $(no_proxy),--build-arg no_proxy=$(no_proxy)) \
  $(if $(filter true,$(ADD_COPYLEFT_SOURCES)),--build-arg COPYLEFT_SOURCES=true)

# All images produced by this Makefile (app + dependency services)
DEP_IMAGES  := $(REGISTRY)vdms-dataprep:$(TAG) $(REGISTRY)multimodal-embedding-serving:$(TAG)
APP_IMAGES  := $(foreach c,$(COMPONENTS),$(REGISTRY)$(c):$(TAG))
ALL_IMAGES  := $(DEP_IMAGES) $(APP_IMAGES)

# ==============================================================================
# Internal Variables
# ==============================================================================

TEST_TARGETS := $(addprefix test-,$(TEST_COMPONENTS))

.PHONY: build build-deps push check-docker check-poetry test clean help list \
        shellcheck pylint eslint \
        trivy-scan trivy-scan-fs trivy-scan-image trivy-scan-config \
        clamav-scan bandit-scan gitleaks-scan codeql-scan \
        $(TEST_TARGETS) \
        get-service-name get-component-names get-image-tags get-context-dirs \
        get-python-version get-node-version get-go-version get-scan-matrix-json \
        deploy deploy-summary deploy-search deploy-dual deploy-unified \
        deploy-stop deploy-clean health-check

# ==============================================================================
# Build Targets
# ==============================================================================

check-docker:
	@command -v docker >/dev/null 2>&1 || \
	  { echo "docker is not installed or not in PATH."; \
	    echo "   Install: https://docs.docker.com/get-docker/"; exit 1; }

check-poetry:
	@command -v poetry >/dev/null 2>&1 || \
	  { echo "poetry is not installed or not in PATH."; \
	    echo "   Required to build the multimodal-embedding wheel."; \
	    echo "   Install: https://python-poetry.org/docs/#installation"; exit 1; }

build: check-docker check-poetry
	@$(if $(REGISTRY),,echo "Warning: No registry prefix set. Images will be tagged without a registry prefix.")
	@echo "Building all application services..."
	@$(foreach component,$(COMPONENTS), \
		echo "  → Building $(component): $(REGISTRY)$(component):$(TAG)"; \
		docker build $(DOCKER_BUILD_ARGS) \
			-t $(REGISTRY)$(component):$(TAG) \
			-f $($(component)_DOCKERFILE) $($(component)_CONTEXT_DIR); \
	)
	@echo "All application services built successfully."

# Build external dependency microservices (vdms-dataprep, multimodal-embedding-serving).
# Requires poetry to build the multimodal-embedding wheel.
build-deps: check-docker check-poetry
	@$(if $(REGISTRY),,echo "Warning: No registry prefix set. Images will be tagged without a registry prefix.")
	@echo "Building dependency microservices..."
	@echo "  → Building vdms-dataprep via upstream build.sh..."
	@if [ -x "$(USERVICES_DIR)/visual-data-preparation-for-retrieval/vdms/build.sh" ]; then \
	  cd "$(USERVICES_DIR)/visual-data-preparation-for-retrieval/vdms" && \
	  REGISTRY_URL="$(REGISTRY_URL)" PROJECT_NAME="$(PROJECT_NAME)" TAG="$(TAG)" ./build.sh; \
	else \
	  echo "vdms build.sh not found or not executable: $(USERVICES_DIR)/visual-data-preparation-for-retrieval/vdms/build.sh"; \
	  exit 1; \
	fi
	@echo "  → Building multimodal-embedding-serving..."
	@if [ -f "$(USERVICES_DIR)/multimodal-embedding-serving/docker/compose.yaml" ]; then \
	  cd "$(USERVICES_DIR)/multimodal-embedding-serving" && \
	  docker build $(DOCKER_BUILD_ARGS) \
	    -t $(REGISTRY)multimodal-embedding-serving:$(TAG) \
	    -f docker/Dockerfile .; \
	else \
	  echo "Dockerfile/compose.yaml not found for multimodal-embedding-serving."; \
	  exit 1; \
	fi
	@echo "All dependency microservices built successfully."

# Push all built images (app services + dependency microservices) to the registry.
# Images are pushed in parallel (backgrounded) to speed up multi-image pushes.
push: check-docker
	@if [ -z "$(REGISTRY)" ]; then \
	  echo "REGISTRY is empty. Refusing to push un-namespaced images to docker.io. Set REGISTRY or REGISTRY_URL+PROJECT_NAME."; \
	  exit 1; \
	fi
	@echo "Pushing images to registry..."
	@pids=""; \
	for image in $(ALL_IMAGES); do \
	  if docker image inspect "$$image" >/dev/null 2>&1; then \
	    ( echo "  → Pushing $$image..."; \
	      if docker push "$$image"; then \
	        echo "  Pushed $$image"; \
	      else \
	        echo "  Failed to push $$image"; \
	        exit 1; \
	      fi \
	    ) & \
	    pids="$$pids $$!"; \
	  else \
	    echo "Image $$image not found locally, skipping."; \
	  fi; \
	done; \
	push_ok=true; \
	for pid in $$pids; do \
	  wait "$$pid" || push_ok=false; \
	done; \
	$$push_ok && echo "All images pushed successfully." || { echo "Some images failed to push."; exit 1; }


# ==============================================================================
# Deploy
# ==============================================================================
#
# All configuration is loaded from .env (auto-created from .env.example on
# first run). Edit .env to set models, ports, and feature flags.
#
# Every deploy target builds all application images from source first (via the
# `build` prerequisite) so that newly built local images are always used instead
# of pulling from a registry. Third-party images (nginx, postgres, etc.) are
# still pulled from the registry when not already cached locally.
#
# Secrets (POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, RABBITMQ_PASSWORD,
# HUGGINGFACE_TOKEN) are intentionally blank in .env.example.
# Supply them before running deploy targets via either:
#
#   Local dev:
#     export POSTGRES_PASSWORD=<value>   # in your shell, then run make deploy-*
#
#   GitHub Actions:
#     env:
#       POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
#       MINIO_ROOT_PASSWORD: ${{ secrets.MINIO_ROOT_PASSWORD }}
#       RABBITMQ_PASSWORD: ${{ secrets.RABBITMQ_PASSWORD }}
#
# Modes:
#   deploy-summary  → summarization pipeline + summary UI
#   deploy-search   → embedding/index/search + search UI
#   deploy-dual     → both pipelines, two separate UIs
#   deploy-unified  → search over summary text in one UI
#
# Lifecycle:
#   deploy-stop     → stop all containers (mode-agnostic, no env vars needed)
#   deploy-clean    → stop all containers and wipe user-data volumes
# ==============================================================================

WAIT_HEALTH_SCRIPT := .github/skills/vss-up/scripts/wait-health.sh

# Load .env into the shell before calling setup.sh.
# Rules:
#   1. Empty values (secrets) are skipped — they must come from the environment.
#   2. Variables already set in the environment are never overridden, so CI
#      secrets (injected via workflow `env:`) always take precedence.
define LOAD_ENV
while IFS= read -r _line; do \
  _k="$${_line%%=*}"; \
  case "$$_k" in \#*|"") continue ;; esac; \
  _v="$${_line#*=}"; \
  [ -z "$$_v" ] && continue; \
  [ -n "$${!_k+set}" ] && continue; \
  export "$$_k=$$_v"; \
done < .env
endef

deploy:
	@echo ""
	@echo "Please specify a deployment mode:"
	@echo "  make deploy-summary   — summarization pipeline + summary UI"
	@echo "  make deploy-search    — embedding/index/search + search UI"
	@echo "  make deploy-dual      — both pipelines, two separate UIs"
	@echo "  make deploy-unified   — search over summary text, one UI"
	@echo ""
	@echo "Lifecycle:"
	@echo "  make deploy-stop      — stop all containers"
	@echo "  make deploy-clean     — stop all containers and wipe data volumes"
	@echo ""
	@exit 1

deploy-summary: build
	@echo "Deploying VSS in summary mode..."
	@bash -c '$(LOAD_ENV) && source setup.sh --stop && source setup.sh --summary'
	@$(WAIT_HEALTH_SCRIPT)
	@echo "VSS summary mode deployed."

deploy-search: build
	@echo "Deploying VSS in search mode..."
	@bash -c '$(LOAD_ENV) && source setup.sh --stop && source setup.sh --search'
	@$(WAIT_HEALTH_SCRIPT)
	@echo "VSS search mode deployed."

deploy-dual: build
	@echo "Deploying VSS in dual (summary + search) mode..."
	@bash -c '$(LOAD_ENV) && source setup.sh --stop && source setup.sh --summary --search'
	@$(WAIT_HEALTH_SCRIPT)
	@echo "VSS dual mode deployed."

deploy-unified: build
	@echo "Deploying VSS in unified mode (search over summaries)..."
	@bash -c '$(LOAD_ENV) && source setup.sh --stop && source setup.sh --summary-and-search'
	@$(WAIT_HEALTH_SCRIPT)
	@echo "VSS unified mode deployed."

deploy-stop:
	@echo "Stopping all VSS containers..."
	@bash -c 'source setup.sh --stop'
	@echo "VSS stack stopped."

deploy-clean:
	@echo "Stopping VSS containers and wiping user-data volumes..."
	@bash -c 'source setup.sh --clean-data'
	@echo "VSS stack stopped and data volumes wiped."

health-check:
	@echo "Checking VSS health..."
	@$(WAIT_HEALTH_SCRIPT)


# ==============================================================================
# Test Targets
# ==============================================================================

test: $(TEST_TARGETS)
	@if [ -z "$(TEST_TARGETS)" ]; then \
		echo "No test components configured."; \
	else \
		echo "All tests completed."; \
	fi

test-pipeline-manager:
	@echo "Running pipeline-manager tests (NestJS/Jest)..."
	@cd $(pipeline-manager_CONTEXT_DIR) && npm install && npm run test:cov
	@echo "pipeline-manager tests complete."

test-vss-ui:
	@echo "Running UI tests (Vite/Vitest)..."
	@cd $(vss-ui_CONTEXT_DIR) && npm install && npm run coverage
	@echo "UI tests complete."

test-video-search:
	@echo "Running video-search tests (pytest)..."
	@cd $(video-search_CONTEXT_DIR) && \
	python3 -m venv .test-venv && \
	source .test-venv/bin/activate && \
	pip install poetry && \
	poetry install --no-root --with dev 2>/dev/null && \
	poetry run pytest \
		--verbose \
		--cov=src \
		--cov-report=html:coverage-video-search \
		--cov-report=term-missing \
		--cov-branch  && \
	deactivate && \
	rm -rf .test-venv
	@echo "video-search tests complete."

test-video-ingestion:
	@echo "Running video-ingestion tests (pytest)..."
	@cd $(video-ingestion_CONTEXT_DIR) && \
	python3 -m venv .test-venv && \
	source .test-venv/bin/activate && \
	pip install -r requirements-test.txt && \
	pytest tests/ \
		--verbose \
		--cov=src \
		--cov-report=html:coverage-video-ingestion \
		--cov-report=term-missing \
		--cov-branch && \
	deactivate && \
	rm -rf .test-venv
	@echo "video-ingestion tests complete."

# ==============================================================================
# Code Quality Targets
# ==============================================================================

shellcheck:
	@echo "Running ShellCheck..."
	@mkdir -p security-results
	@find . -type f \( -name "*.sh" -o -name "*.bash" \) -print0 | xargs -0 -r \
		shellcheck --format=json > security-results/shellcheck-report-$(SERVICE_NAME).json 2>/dev/null || true
	@echo "Report: security-results/shellcheck-report-$(SERVICE_NAME).json"

pylint:
	@echo "Running Pylint..."
	@mkdir -p security-results
	@# --- search-ms (poetry-based) ---
	@echo "  → Linting search-ms..."
	@cd $(video-search_CONTEXT_DIR) && \
	python3 -m venv .pylint-venv && \
	source .pylint-venv/bin/activate && \
	pip install poetry && \
	poetry install --no-root --with dev 2>/dev/null || true && \
	poetry add --group dev pylint 2>/dev/null || true && \
	( \
		echo "[MESSAGES CONTROL]"; \
		echo "disable=C0111,C0103,R0903,R0913,W0613,W0622,R0801,R0902,R0914,R0915,R0912,C0301,C0302"; \
		echo ""; \
		echo "[FORMAT]"; \
		echo "max-line-length=120"; \
		echo ""; \
		echo "[REPORTS]"; \
		echo "output-format=json"; \
		echo "reports=yes"; \
	) > .pylintrc && \
	( find src/ -type f -name "*.py" -exec poetry run pylint --rcfile=.pylintrc {} + ; \
	  poetry run pylint --rcfile=.pylintrc server.py 2>/dev/null || true ) \
		> ../security-results/pylint-report-search-ms.json 2>/dev/null || true && \
	deactivate && \
	rm -rf .pylint-venv .pylintrc
	@echo "search-ms: security-results/pylint-report-search-ms.json"
	@# --- video-ingestion (pip-based) ---
	@echo "  → Linting video-ingestion..."
	@cd $(video-ingestion_CONTEXT_DIR) && \
	python3 -m venv .pylint-venv && \
	source .pylint-venv/bin/activate && \
	pip install -r requirements.txt pylint && \
	( \
		echo "[MESSAGES CONTROL]"; \
		echo "disable=C0111,C0103,R0903,R0913,W0613,W0622,R0801,R0902,R0914,R0915,R0912,C0301,C0302"; \
		echo ""; \
		echo "[FORMAT]"; \
		echo "max-line-length=120"; \
		echo ""; \
		echo "[REPORTS]"; \
		echo "output-format=json"; \
		echo "reports=yes"; \
	) > .pylintrc && \
	find src/ -type f -name "*.py" -exec pylint --rcfile=.pylintrc {} + \
		> ../security-results/pylint-report-video-ingestion.json 2>/dev/null || true && \
	deactivate && \
	rm -rf .pylint-venv .pylintrc
	@echo "video-ingestion: security-results/pylint-report-video-ingestion.json"

eslint:
	@echo "Running ESLint..."
	@mkdir -p security-results
	@# --- pipeline-manager (NestJS/TypeScript) ---
	@echo "  → Linting pipeline-manager..."
	@cd $(pipeline-manager_CONTEXT_DIR) && \
	npm install && \
	npx eslint . --format json --output-file ../security-results/eslint-report-pipeline-manager.json || true
	@echo "pipeline-manager: security-results/eslint-report-pipeline-manager.json"
	@# --- vss-ui (React/Vite/TypeScript) ---
	@echo "  → Linting vss-ui..."
	@cd $(vss-ui_CONTEXT_DIR) && \
	npm install && \
	npx eslint . --format json --output-file ../../security-results/eslint-report-vss-ui.json || true
	@echo "vss-ui: security-results/eslint-report-vss-ui.json"

# ==============================================================================
# Security Scan Targets
# ==============================================================================

trivy-scan: trivy-scan-fs trivy-scan-image trivy-scan-config
	@echo "Creating security scan archive..."
	@cd security-results && zip -r trivy-scan-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).zip trivy-* 2>/dev/null || true
	@echo "All Trivy scans complete. Reports: security-results/trivy-*"

# Trivy HTML template - auto-detect or download
TRIVY_HTML_TPL_URL := https://raw.githubusercontent.com/aquasecurity/trivy/main/pkg/report/templates/html.tpl
TRIVY_HTML_TPL_LOCAL := security-results/.trivy-html.tpl

define ENSURE_TRIVY_HTML_TPL
	if [ -f "/usr/local/share/trivy/templates/html.tpl" ]; then \
		TRIVY_HTML_TPL="/usr/local/share/trivy/templates/html.tpl"; \
	elif [ -f "/usr/share/trivy/templates/html.tpl" ]; then \
		TRIVY_HTML_TPL="/usr/share/trivy/templates/html.tpl"; \
	else \
		echo "  → Trivy HTML template not found locally, downloading..."; \
		mkdir -p security-results; \
		curl -sSL -o $(TRIVY_HTML_TPL_LOCAL) $(TRIVY_HTML_TPL_URL) || \
			wget -qO $(TRIVY_HTML_TPL_LOCAL) $(TRIVY_HTML_TPL_URL) || \
			{ echo "Could not download HTML template. HTML reports will be skipped."; TRIVY_HTML_TPL=""; }; \
		TRIVY_HTML_TPL="$(TRIVY_HTML_TPL_LOCAL)"; \
	fi
endef

trivy-scan-fs:
	@echo "Running Trivy Filesystem Scan..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	scan_dir() { \
		local dir="$$1"; local suffix="$$2"; \
		echo "  → Scanning $$dir ..."; \
		trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format json \
			--output security-results/trivy-fs-$(SERVICE_NAME)$$suffix.json "$$dir"; \
		trivy fs --format spdx-json \
			--output security-results/trivy-fs-$(SERVICE_NAME)$$suffix.spdx.json "$$dir"; \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-fs-$(SERVICE_NAME)$$suffix.html "$$dir"; \
		fi; \
	}; \
	scan_dir "." ""; \
	for d in $(DEP_SCAN_DIRS); do \
		if [ -d "$$d" ]; then \
			suffix="-$$(basename $$d)"; \
			scan_dir "$$d" "$$suffix"; \
		else \
			echo "build-dep dir not found, skipping: $$d"; \
		fi; \
	done; \
	echo "Filesystem scan complete: security-results/trivy-fs-$(SERVICE_NAME)*.{json,spdx.json,html}"

trivy-scan-image: build
	@echo "Running Trivy Image Scans..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	for component in $(COMPONENTS) $(DEP_COMPONENTS); do \
		echo "  → Scanning $$component image..."; \
		if [ -z "$$(docker images -q $(REGISTRY)$$component:$(TAG) 2>/dev/null)" ]; then \
			echo "Image '$(REGISTRY)$$component:$(TAG)' not found, skipping."; \
		else \
			trivy image --severity HIGH,CRITICAL --ignore-unfixed --format json \
				--output security-results/trivy-image-$(SERVICE_NAME)-$$component.json \
				$(REGISTRY)$$component:$(TAG); \
			trivy image --format spdx-json \
				--output security-results/trivy-image-$(SERVICE_NAME)-$$component.spdx.json \
				$(REGISTRY)$$component:$(TAG); \
			if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
				trivy image --severity HIGH,CRITICAL --ignore-unfixed --format template \
					--template "@$$TRIVY_HTML_TPL" \
					--output security-results/trivy-image-$(SERVICE_NAME)-$$component.html \
					$(REGISTRY)$$component:$(TAG); \
			fi; \
		fi; \
	done
	@echo "Image scans complete: security-results/trivy-image-*.{json,spdx.json,html}"

trivy-scan-config:
	@echo "Running Trivy Config Scans..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	$(foreach component,$(COMPONENTS), \
		echo "  → Scanning $(component) Dockerfile..."; \
		trivy config --severity HIGH,CRITICAL --format json \
			--output security-results/trivy-config-$(SERVICE_NAME)-$(component).json \
			--file-patterns "dockerfile:Dockerfile" $($(component)_CONTEXT_DIR); \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy config --severity HIGH,CRITICAL --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-config-$(SERVICE_NAME)-$(component).html \
				--file-patterns "dockerfile:Dockerfile" $($(component)_CONTEXT_DIR); \
		fi; \
	)
	@echo "Config scans complete: security-results/trivy-config-*.{json,html}"

clamav-scan:
	@echo "Running ClamAV Antivirus Scan..."
	@mkdir -p security-results
	@clamscan -r . \
		--exclude-dir=.git \
		--exclude-dir=node_modules \
		--exclude-dir=venv \
		--exclude-dir=chart \
		--exclude-dir=cli \
		> security-results/clamav-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).txt 2>&1 || true
	@echo "ClamAV scan complete: security-results/clamav-*"

bandit-scan:
	@echo "Running Bandit Security Scan..."
	@mkdir -p security-results
	@python3 -m venv bandit-venv && \
	source bandit-venv/bin/activate && \
	pip install --upgrade pip && \
	pip install bandit[toml] && \
	CONFIG_OPT=""; \
	if [ -f "pyproject.toml" ]; then CONFIG_OPT="-c pyproject.toml"; fi; \
	echo "Generating TXT Report (matches CI)..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f txt -o security-results/bandit-report-$(SERVICE_NAME).txt || true && \
	echo "Generating JSON Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f json -o security-results/bandit-report-$(SERVICE_NAME).json || true && \
	echo "Generating HTML Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f html -o security-results/bandit-report-$(SERVICE_NAME).html || true && \
	deactivate && \
	rm -rf bandit-venv
	@echo "Bandit scan complete. Check security-results/ for txt, json, and html reports."

gitleaks-scan:
	@echo "Running Gitleaks Secrets Scan..."
	@mkdir -p security-results
	@gitleaks dir . -v \
		-r security-results/gitleaks-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).json || true
	@echo "Gitleaks scan complete: security-results/gitleaks-*"

codeql-scan:
	@echo "Running CodeQL Security Analysis..."
	@if ! command -v codeql >/dev/null 2>&1; then \
		echo ""; \
		echo "CodeQL CLI is not installed."; \
		echo "Install: https://github.com/github/codeql-cli-binaries/releases"; \
		echo ""; \
		exit 1; \
	fi

	@mkdir -p security-results
	@echo ""
	@# --- Download / verify required query packs ---
	@echo "→ Checking CodeQL Python query pack..."
	@if ! codeql resolve qlpacks 2>/dev/null | grep -q 'codeql/python-queries'; then \
		echo "Downloading codeql/python-queries..."; \
		codeql pack download codeql/python-queries; \
	else \
		echo "codeql/python-queries already available."; \
	fi

	@echo "→ Checking CodeQL JavaScript/TypeScript query pack..."
	@if ! codeql resolve qlpacks 2>/dev/null | grep -q 'codeql/javascript-queries'; then \
		echo "Downloading codeql/javascript-queries..."; \
		codeql pack download codeql/javascript-queries; \
	else \
		echo "codeql/javascript-queries already available."; \
	fi
	@echo ""

	@# --- Python: search-ms ---
	@echo "→ Creating CodeQL database for Python (search-ms)..."
	@codeql database create security-results/codeql-db-python-search-ms \
		--language=python \
		--source-root=search-ms \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on search-ms (SARIF)..."
	@codeql database analyze security-results/codeql-db-python-search-ms \
		codeql/python-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-python-search-ms.sarif || true
	@echo "→ Running CodeQL analysis on search-ms (CSV)..."
	@codeql database analyze security-results/codeql-db-python-search-ms \
		codeql/python-queries \
		--format=csv \
		--output=security-results/codeql-python-search-ms.csv || true
	@echo "Python (search-ms) analysis complete."
	@echo ""

	@# --- Python: video-ingestion ---
	@echo "→ Creating CodeQL database for Python (video-ingestion)..."
	@codeql database create security-results/codeql-db-python-video-ingestion \
		--language=python \
		--source-root=video-ingestion \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on video-ingestion (SARIF)..."
	@codeql database analyze security-results/codeql-db-python-video-ingestion \
		codeql/python-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-python-video-ingestion.sarif || true
	@echo "→ Running CodeQL analysis on video-ingestion (CSV)..."
	@codeql database analyze security-results/codeql-db-python-video-ingestion \
		codeql/python-queries \
		--format=csv \
		--output=security-results/codeql-python-video-ingestion.csv || true
	@echo "Python (video-ingestion) analysis complete."
	@echo ""

	@# --- JavaScript/TypeScript: pipeline-manager ---
	@echo "→ Creating CodeQL database for TypeScript (pipeline-manager)..."
	@codeql database create security-results/codeql-db-js-pipeline-manager \
		--language=javascript \
		--source-root=pipeline-manager \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on pipeline-manager (SARIF)..."
	@codeql database analyze security-results/codeql-db-js-pipeline-manager \
		codeql/javascript-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-js-pipeline-manager.sarif || true
	@echo "→ Running CodeQL analysis on pipeline-manager (CSV)..."
	@codeql database analyze security-results/codeql-db-js-pipeline-manager \
		codeql/javascript-queries \
		--format=csv \
		--output=security-results/codeql-js-pipeline-manager.csv || true
	@echo "TypeScript (pipeline-manager) analysis complete."
	@echo ""

	@# --- JavaScript/TypeScript: vss-ui ---
	@echo "→ Creating CodeQL database for TypeScript (vss-ui)..."
	@codeql database create security-results/codeql-db-js-vss-ui \
		--language=javascript \
		--source-root=ui/react \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on vss-ui (SARIF)..."
	@codeql database analyze security-results/codeql-db-js-vss-ui \
		codeql/javascript-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-js-vss-ui.sarif || true
	@echo "→ Running CodeQL analysis on vss-ui (CSV)..."
	@codeql database analyze security-results/codeql-db-js-vss-ui \
		codeql/javascript-queries \
		--format=csv \
		--output=security-results/codeql-js-vss-ui.csv || true
	@echo "TypeScript (vss-ui) analysis complete."
	@echo ""
	@echo "CodeQL scan complete: security-results/codeql-*.{sarif,csv}"

# ==============================================================================
# Info & Utility Targets
# ==============================================================================

list:
	@echo "══════════════════════════════════════════════════"
	@echo "Configuration - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Project:"
	@echo "  Service Name:     $(SERVICE_NAME)"
	@echo "  Version:          $(VERSION)"
	@echo "  Tag:              $(TAG)"
	@echo "  Registry:         $(if $(REGISTRY),$(REGISTRY),(none — local images))"
	@echo "  Python:           $(PYTHON_VERSION)"
	@echo "  Node:             $(NODE_VERSION)"
	@echo "  Go:               $(GO_VERSION)"
	@echo ""
	@echo "Application Images:"
	@$(foreach component,$(COMPONENTS), echo "  • $(REGISTRY)$(component):$(TAG)";)
	@echo ""
	@echo "Dependency Images:"
	@$(foreach img,$(DEP_IMAGES), echo "  • $(img)";)
	@echo ""
	@echo "Test Components:"
	@$(foreach component,$(TEST_COMPONENTS), echo "  • $(component)";)

clean:
	@echo "Removing Docker images..."
	@$(foreach component,$(COMPONENTS), \
		docker rmi -f $(REGISTRY)$(component):$(TAG) 2>/dev/null || true; \
	)
	@echo "Cleanup complete."

# ==============================================================================
# CI/CD Targets
# ==============================================================================

get-service-name:
	@echo $(SERVICE_NAME)

get-component-names:
	@echo "$(COMPONENTS)"

get-image-tags:
	@$(foreach component,$(COMPONENTS), echo "$(REGISTRY)$(component):$(TAG)";)

get-context-dirs:
	@$(foreach component,$(COMPONENTS), echo "$($(component)_CONTEXT_DIR)";)

get-python-version:
	@echo $(PYTHON_VERSION)

get-node-version:
	@echo $(NODE_VERSION)

get-go-version:
	@echo $(GO_VERSION)

get-scan-matrix-json:
	@printf '{"include":['
	@$(foreach component,$(COMPONENTS), \
		$(eval COMMA := $(if $(findstring $(component),$(firstword $(COMPONENTS))),,',')) \
		printf '%s' '$(COMMA){"name":"$(component)","image":"$(REGISTRY)$(component):$(TAG)","context":"$($(component)_CONTEXT_DIR)","dockerfile":"$($(component)_DOCKERFILE)"}'; \
	)
	@printf ']}\n'

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║        Video Search & Summarization - Makefile                   ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "BUILD & TEST"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  build            Build application service images (video-ingestion,"
	@echo "                   pipeline-manager, video-search, vss-ui)"
	@echo "  build-deps       Build dependency images (vdms-dataprep,"
	@echo "                   multimodal-embedding-serving) — requires poetry"
	@echo "  push             Push all built images to the registry"
	@echo "  test             Run all unit tests"
	@echo "  test-pipeline-manager   Run pipeline-manager tests (NestJS/Jest)"
	@echo "  test-vss-ui             Run UI tests (Vite/Vitest)"
	@echo "  test-video-search       Run video-search tests (pytest)"
	@echo "  test-video-ingestion    Run video-ingestion tests (pytest)"
	@echo ""
	@echo "  Image tag:  TAG=<tag>  (default: $(TAG))"
	@echo "  Registry:   REGISTRY=<prefix>/   or   REGISTRY_URL=<url> PROJECT_NAME=<proj>"
	@echo "  Proxies:    http_proxy=  https_proxy=  no_proxy=  (omitted when unset)"
	@echo "  Copyleft:   ADD_COPYLEFT_SOURCES=true  (injects COPYLEFT_SOURCES build-arg)"
	@echo ""
	@echo "DEPLOY"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  deploy-summary   Deploy summarization pipeline + summary UI"
	@echo "  deploy-search    Deploy embedding/index/search + search UI"
	@echo "  deploy-dual      Deploy both pipelines with two separate UIs"
	@echo "  deploy-unified   Deploy search over summary text in one UI"
	@echo "  deploy-stop      Stop all VSS containers"
	@echo "  deploy-clean     Stop all containers and wipe user-data volumes"
	@echo "  health-check     Wait for Pipeline Manager health and print URLs"
	@echo ""
	@echo "  Config:  edit .env (auto-created from .env.example on first make run)"
	@echo "  Secrets: export POSTGRES_PASSWORD=.. MINIO_ROOT_PASSWORD=.. etc. in"
	@echo "           your shell, or inject via GitHub Actions 'env:' block."
	@echo ""
	@echo "CODE QUALITY & SECURITY"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  shellcheck       Run ShellCheck on shell scripts"
	@echo "  pylint           Run Pylint on Python code (search-ms, video-ingestion)"
	@echo "  eslint           Run ESLint on TypeScript code (pipeline-manager, vss-ui)"
	@echo "  trivy-scan       Run all Trivy scans"
	@echo "  trivy-scan-fs    Run Trivy filesystem scan"
	@echo "  trivy-scan-image Run Trivy image scans"
	@echo "  trivy-scan-config Run Trivy Dockerfile scans"
	@echo "  clamav-scan      Run ClamAV antivirus scan"
	@echo "  bandit-scan      Run Bandit security scan"
	@echo "  gitleaks-scan    Run Gitleaks secrets scan"
	@echo "  codeql-scan      Run CodeQL security analysis (Python + TypeScript)"
	@echo ""
	@echo "UTILITIES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  list             Show build configuration"
	@echo "  clean            Remove built application Docker images"
	@echo "  help             Show this help message"
	@echo ""
	@echo "EXAMPLES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  # Build all images"
	@echo "  make build"
	@echo ""
	@echo "  # Build with a registry prefix and custom tag"
	@echo "  make build REGISTRY_URL=myregistry.io PROJECT_NAME=myproject TAG=v1.2"
	@echo ""
	@echo "  # Build with proxy (proxy args omitted when not set)"
	@echo "  make build http_proxy=http://proxy:3128 https_proxy=http://proxy:3128"
	@echo ""
	@echo "  # Build dependency microservices, then push everything"
	@echo "  make build-deps build REGISTRY=myregistry.io/myproject/ TAG=v1.2"
	@echo "  make push        REGISTRY=myregistry.io/myproject/ TAG=v1.2"
	@echo ""
	@echo "  # Run all tests"
	@echo "  make test"
	@echo ""
	@echo "  # Deploy (export secrets first, then deploy)"
	@echo "  export POSTGRES_PASSWORD=secret MINIO_ROOT_PASSWORD=secret \\"
	@echo "         RABBITMQ_PASSWORD=secret"
	@echo "  make deploy-summary"
	@echo ""
	@echo "  # Run all security scans"
	@echo "  make trivy-scan bandit-scan gitleaks-scan codeql-scan"
	@echo ""
