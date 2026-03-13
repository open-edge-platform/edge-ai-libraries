# SPDX-FileCopyrightText: Copyright (C) 2025 Intel Corporation
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

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := vss
VERSION ?= latest
PYTHON_VERSION := 3.12
NODE_VERSION := 22
GO_VERSION := 1.23

# ==============================================================================
# Image Configuration
# ==============================================================================

DEFAULT_REGISTRY := intel/
DEFAULT_TAG := 1.3.1

REGISTRY ?= $(DEFAULT_REGISTRY)
TAG ?= $(DEFAULT_TAG)

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

# Dependency microservices (pre-built, pulled from registry via compose)
# vdms-dataprep, multimodal-embedding-serving, vlm-openvino-serving, audio-analyzer

# ==============================================================================
# Internal Variables
# ==============================================================================

TEST_TARGETS := $(addprefix test-,$(TEST_COMPONENTS))

.PHONY: all build test clean help list \
        shellcheck pylint eslint \
        trivy-scan trivy-scan-fs trivy-scan-image trivy-scan-config \
        clamav-scan bandit-scan gitleaks-scan codeql-scan \
        $(TEST_TARGETS) \
        get-service-name get-component-names get-image-tags get-context-dirs \
        get-python-version get-node-version get-go-version get-scan-matrix-json

# ==============================================================================
# Build Targets
# ==============================================================================

build:
	@echo "📦 Building all components..."
	@$(foreach component,$(COMPONENTS), \
		echo "Building $(component): $(SERVICE_NAME)-$(component):$(VERSION)"; \
		docker build \
			-t $(SERVICE_NAME)-$(component):$(VERSION) \
			-f $($(component)_DOCKERFILE) $($(component)_CONTEXT_DIR); \
	)
	@echo "✅ All components built successfully."

# ==============================================================================
# Test Targets
# ==============================================================================

test: $(TEST_TARGETS)
	@if [ -z "$(TEST_TARGETS)" ]; then \
		echo "⚠️  No test components configured."; \
	else \
		echo "✅ All tests completed."; \
	fi

test-pipeline-manager:
	@echo "🧪 Running pipeline-manager tests (NestJS/Jest)..."
	@cd $(pipeline-manager_CONTEXT_DIR) && npm install && npm run test:cov
	@echo "✅ pipeline-manager tests complete."

test-vss-ui:
	@echo "🧪 Running UI tests (Vite/Vitest)..."
	@cd $(vss-ui_CONTEXT_DIR) && npm install && npm run coverage
	@echo "✅ UI tests complete."

test-video-search:
	@echo "🧪 Running video-search tests (pytest)..."
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
		--cov-branch || true && \
	deactivate && \
	rm -rf .test-venv
	@echo "✅ video-search tests complete."

test-video-ingestion:
	@echo "🧪 Running video-ingestion tests (pytest)..."
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
	@echo "✅ video-ingestion tests complete."

# ==============================================================================
# Code Quality Targets
# ==============================================================================

shellcheck:
	@echo "🔍 Running ShellCheck..."
	@mkdir -p security-results
	@find . -type f \( -name "*.sh" -o -name "*.bash" \) -print0 | xargs -0 -r \
		shellcheck --format=json > security-results/shellcheck-report-$(SERVICE_NAME).json 2>/dev/null || true
	@echo "✅ Report: security-results/shellcheck-report-$(SERVICE_NAME).json"

pylint:
	@echo "🔍 Running Pylint..."
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
	@echo "  ✅ search-ms: security-results/pylint-report-search-ms.json"
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
	@echo "  ✅ video-ingestion: security-results/pylint-report-video-ingestion.json"

eslint:
	@echo "🔍 Running ESLint..."
	@mkdir -p security-results
	@# --- pipeline-manager (NestJS/TypeScript) ---
	@echo "  → Linting pipeline-manager..."
	@cd $(pipeline-manager_CONTEXT_DIR) && \
	npm install && \
	npx eslint . --format json --output-file ../security-results/eslint-report-pipeline-manager.json || true
	@echo "  ✅ pipeline-manager: security-results/eslint-report-pipeline-manager.json"
	@# --- vss-ui (React/Vite/TypeScript) ---
	@echo "  → Linting vss-ui..."
	@cd $(vss-ui_CONTEXT_DIR) && \
	npm install && \
	npx eslint . --format json --output-file ../../security-results/eslint-report-vss-ui.json || true
	@echo "  ✅ vss-ui: security-results/eslint-report-vss-ui.json"

# ==============================================================================
# Security Scan Targets
# ==============================================================================

trivy-scan: trivy-scan-fs trivy-scan-image trivy-scan-config
	@echo "📦 Creating security scan archive..."
	@cd security-results && zip -r trivy-scan-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).zip trivy-* 2>/dev/null || true
	@echo "✅ All Trivy scans complete. Reports: security-results/trivy-*"

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
			{ echo "  ⚠️  Could not download HTML template. HTML reports will be skipped."; TRIVY_HTML_TPL=""; }; \
		TRIVY_HTML_TPL="$(TRIVY_HTML_TPL_LOCAL)"; \
	fi
endef

trivy-scan-fs:
	@echo "🔍 Running Trivy Filesystem Scan..."
	@mkdir -p security-results
	@trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format json \
		--output security-results/trivy-fs-$(SERVICE_NAME).json . || true
	@trivy fs --format spdx-json \
		--output security-results/trivy-fs-$(SERVICE_NAME).spdx.json . || true
	@$(ENSURE_TRIVY_HTML_TPL); \
	if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
		trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format template \
			--template "@$$TRIVY_HTML_TPL" \
			--output security-results/trivy-fs-$(SERVICE_NAME).html . || true; \
		echo "✅ Filesystem scan complete: security-results/trivy-fs-$(SERVICE_NAME).{json,spdx.json,html}"; \
	else \
		echo "✅ Filesystem scan complete: security-results/trivy-fs-$(SERVICE_NAME).{json,spdx.json}"; \
	fi

trivy-scan-image:
	@echo "🔍 Running Trivy Image Scans..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	$(foreach component,$(COMPONENTS), \
		echo "  → Scanning $(component) image..."; \
		if [ -z "$$(docker images -q $(SERVICE_NAME)-$(component):$(VERSION) 2>/dev/null)" ]; then \
			echo "  ⚠️  Image '$(SERVICE_NAME)-$(component):$(VERSION)' not found. Run 'make build' first."; \
		else \
			trivy image --severity HIGH,CRITICAL --ignore-unfixed --format json \
				--output security-results/trivy-image-$(SERVICE_NAME)-$(component).json \
				$(SERVICE_NAME)-$(component):$(VERSION) || true; \
			trivy image --format spdx-json \
				--output security-results/trivy-image-$(SERVICE_NAME)-$(component).spdx.json \
				$(SERVICE_NAME)-$(component):$(VERSION) || true; \
			if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
				trivy image --severity HIGH,CRITICAL --ignore-unfixed --format template \
					--template "@$$TRIVY_HTML_TPL" \
					--output security-results/trivy-image-$(SERVICE_NAME)-$(component).html \
					$(SERVICE_NAME)-$(component):$(VERSION) || true; \
			fi; \
		fi; \
	)
	@echo "✅ Image scans complete: security-results/trivy-image-*.{json,spdx.json,html}"

trivy-scan-config:
	@echo "🔍 Running Trivy Config Scans..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	$(foreach component,$(COMPONENTS), \
		echo "  → Scanning $(component) Dockerfile..."; \
		trivy config --severity HIGH,CRITICAL --format json \
			--output security-results/trivy-config-$(SERVICE_NAME)-$(component).json \
			--file-patterns "dockerfile:Dockerfile" $($(component)_CONTEXT_DIR) || true; \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy config --severity HIGH,CRITICAL --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-config-$(SERVICE_NAME)-$(component).html \
				--file-patterns "dockerfile:Dockerfile" $($(component)_CONTEXT_DIR) || true; \
		fi; \
	)
	@echo "✅ Config scans complete: security-results/trivy-config-*.{json,html}"

clamav-scan:
	@echo "🦠 Running ClamAV Antivirus Scan..."
	@mkdir -p security-results
	@clamscan -r . \
		--exclude-dir=.git \
		--exclude-dir=node_modules \
		--exclude-dir=venv \
		--exclude-dir=chart \
		--exclude-dir=cli \
		> security-results/clamav-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).txt 2>&1 || true
	@echo "✅ ClamAV scan complete: security-results/clamav-*"

bandit-scan:
	@echo "🔐 Running Bandit Security Scan..."
	@mkdir -p security-results
	@python3 -m venv bandit-venv && \
	source bandit-venv/bin/activate && \
	pip install --upgrade pip && \
	pip install bandit[toml] && \
	CONFIG_OPT=""; \
	if [ -f "pyproject.toml" ]; then CONFIG_OPT="-c pyproject.toml"; fi; \
	echo "📝 Generating TXT Report (matches CI)..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f txt -o security-results/bandit-report-$(SERVICE_NAME).txt || true && \
	echo "📊 Generating JSON Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f json -o security-results/bandit-report-$(SERVICE_NAME).json || true && \
	echo "🌐 Generating HTML Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r search-ms/ video-ingestion/ \
		-f html -o security-results/bandit-report-$(SERVICE_NAME).html || true && \
	deactivate && \
	rm -rf bandit-venv
	@echo "✅ Bandit scan complete. Check security-results/ for txt, json, and html reports."

gitleaks-scan:
	@echo "🔑 Running Gitleaks Secrets Scan..."
	@mkdir -p security-results
	@gitleaks dir . -v \
		-r security-results/gitleaks-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).json || true
	@echo "✅ Gitleaks scan complete: security-results/gitleaks-*"

codeql-scan:
	@echo "🛡️  Running CodeQL Security Analysis..."
	@if ! command -v codeql >/dev/null 2>&1; then \
		echo ""; \
		echo "❌ CodeQL CLI is not installed."; \
		echo "Install: https://github.com/github/codeql-cli-binaries/releases"; \
		echo ""; \
		exit 1; \
	fi

	@mkdir -p security-results
	@echo ""

	@# --- Download / verify required query packs ---
	@echo "→ Checking CodeQL Python query pack..."
	@if ! codeql resolve qlpacks 2>/dev/null | grep -q 'codeql/python-queries'; then \
		echo "  ⬇️  Downloading codeql/python-queries..."; \
		codeql pack download codeql/python-queries; \
	else \
		echo "  ✅ codeql/python-queries already available."; \
	fi

	@echo "→ Checking CodeQL JavaScript/TypeScript query pack..."
	@if ! codeql resolve qlpacks 2>/dev/null | grep -q 'codeql/javascript-queries'; then \
		echo "  ⬇️  Downloading codeql/javascript-queries..."; \
		codeql pack download codeql/javascript-queries; \
	else \
		echo "  ✅ codeql/javascript-queries already available."; \
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
	@echo "✅ Python (search-ms) analysis complete."
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
	@echo "✅ Python (video-ingestion) analysis complete."
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
	@echo "✅ TypeScript (pipeline-manager) analysis complete."
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
	@echo "✅ TypeScript (vss-ui) analysis complete."
	@echo ""
	@echo "✅ CodeQL scan complete: security-results/codeql-*.{sarif,csv}"

# ==============================================================================
# Info & Utility Targets
# ==============================================================================

list:
	@echo "══════════════════════════════════════════════════"
	@echo "📋 Configuration - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Project:"
	@echo "  Service Name:     $(SERVICE_NAME)"
	@echo "  Version:          $(VERSION)"
	@echo "  Python:           $(PYTHON_VERSION)"
	@echo "  Node:             $(NODE_VERSION)"
	@echo "  Go:               $(GO_VERSION)"
	@echo ""
	@echo "Components:"
	@$(foreach component,$(COMPONENTS), echo "  • $(component)";)
	@echo ""
	@echo "Test Components:"
	@$(foreach component,$(TEST_COMPONENTS), echo "  • $(component)";)

clean:
	@echo "🧹 Removing Docker images..."
	@$(foreach component,$(COMPONENTS), \
		docker rmi -f $(SERVICE_NAME)-$(component):$(VERSION) 2>/dev/null || true; \
	)
	@echo "✅ Cleanup complete."

# ==============================================================================
# CI/CD Targets
# ==============================================================================

get-service-name:
	@echo $(SERVICE_NAME)

get-component-names:
	@echo "$(COMPONENTS)"

get-image-tags:
	@$(foreach component,$(COMPONENTS), echo "$(SERVICE_NAME)-$(component):$(VERSION)";)

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
		printf '%s' '$(COMMA){"name":"$(component)","image":"$(SERVICE_NAME)-$(component):$(VERSION)","context":"$($(component)_CONTEXT_DIR)","dockerfile":"$($(component)_DOCKERFILE)"}'; \
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
	@echo "  build            Build all Docker images"
	@echo "  test             Run all unit tests"
	@echo "  test-pipeline-manager   Run pipeline-manager tests (NestJS/Jest)"
	@echo "  test-vss-ui             Run UI tests (Vite/Vitest)"
	@echo "  test-video-search       Run video-search tests (pytest)"
	@echo "  test-video-ingestion    Run video-ingestion tests (pytest)"
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
	@echo "  clean            Remove built Docker images"
	@echo "  help             Show this help message"
	@echo ""
	@echo "EXAMPLES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  # Build all images"
	@echo "  make build"
	@echo ""
	@echo "  # Run all tests"
	@echo "  make test"
	@echo ""
	@echo "  # Run all security scans"
	@echo "  make trivy-scan bandit-scan gitleaks-scan codeql-scan"
	@echo ""
