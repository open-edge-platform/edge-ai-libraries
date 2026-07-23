# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Model Download - Makefile
# ==============================================================================
#
# Thin wrapper around this component's existing scripts and tooling.
#
# Quick Start:
#   make help          - Show all available commands
#   make build         - Build the Docker image via scripts/run_service.sh
#   make deploy        - Start the service via scripts/run_service.sh
#   make deploy-down   - Stop the service via scripts/run_service.sh
#   make test          - Run unit tests with coverage
#   make lint          - Run pylint on src/
#   make shellcheck    - Run ShellCheck on shell scripts
#   make pylint        - Run Pylint security report (JSON) on src/
#   make trivy-scan    - Run all Trivy security scans
#   make clamav-scan   - Run ClamAV antivirus scan
#   make bandit-scan   - Run Bandit security scan
#   make gitleaks-scan - Run Gitleaks secrets scan
#   make codeql-scan   - Run CodeQL security analysis (Python)
#   make clean         - Remove caches and coverage artifacts
# Example: override TAG, ENABLED_PLUGINS and MODEL_PATH at runtime (these take
# priority over the same values in .env):
#   make deploy TAG=v1.2 ENABLED_PLUGINS=huggingface,ollama MODEL_PATH=~/models/
#
# ==============================================================================

SHELL := /bin/bash

# Auto-create .env from .env.example if it doesn't exist yet.
$(if $(filter build deploy deploy-down,$(MAKECMDGOALS)),$(shell [ -f .env ] || cp .env.example .env),)

# Load registry/tag defaults from .env at parse time so that `make build`
# and `make up` honour .env without requiring shell exports.
ifneq (,$(wildcard .env))
  _env_REGISTRY := $(shell grep -m1 '^REGISTRY=' .env 2>/dev/null | cut -d= -f2-)
  _env_TAG      := $(shell grep -m1 '^TAG=' .env 2>/dev/null | cut -d= -f2-)
endif

# Image registry/tag, forwarded to scripts/run_service.sh (see docker/compose.yaml).
REGISTRY ?= $(_env_REGISTRY)
TAG ?= $(if $(_env_TAG),$(_env_TAG),latest)

SERVICE_NAME := model-download

# Local, auto-installed copies of security-scan CLIs that aren't preinstalled
# (kept out of PATH/system dirs so `make` never needs sudo).
TOOLS_DIR := .tools
GITLEAKS_VERSION := 8.30.1
CODEQL_VERSION := v2.26.1

.PHONY: help build deploy deploy-down test lint clean \
        shellcheck pylint \
        trivy-scan trivy-scan-fs trivy-scan-image trivy-scan-config \
        clamav-scan bandit-scan gitleaks-scan codeql-scan

help:
	@echo "Model Download - Makefile Commands"
	@echo "==================================="
	@echo "build   - Build the Docker image (scripts/run_service.sh --build)"
	@echo "deploy      - Start the service (scripts/run_service.sh up)"
	@echo "deploy-down    - Stop the service (scripts/run_service.sh down)"
	@echo "test    - Run unit tests with coverage"
	@echo "lint    - Run pylint on src/"
	@echo "clean   - Remove caches and coverage artifacts"
	@echo ""
	@echo "Config:  edit .env (auto-created from .env.example on first"
	@echo "         'make build'/'make up'/'make down')"
	@echo "Secrets: export GETI_TOKEN=.. HUGGINGFACEHUB_API_TOKEN=.. etc. in"
	@echo "         your shell before running build/up (never store secrets in .env)"
	@echo ""
	@echo "Code Quality & Security Scans"
	@echo "------------------------------"
	@echo "shellcheck    - Run ShellCheck on shell scripts"
	@echo "pylint        - Run Pylint security report (JSON) on src/"
	@echo "trivy-scan    - Run all Trivy scans (fs, image, config)"
	@echo "clamav-scan   - Run ClamAV antivirus scan"
	@echo "bandit-scan   - Run Bandit security scan"
	@echo "gitleaks-scan - Run Gitleaks secrets scan"
	@echo "codeql-scan   - Run CodeQL security analysis (Python)"
	@echo "Reports are written to security-results/"

build:
	@REGISTRY="$(REGISTRY)" TAG="$(TAG)" bash -c 'source scripts/run_service.sh --build'

deploy:
	@REGISTRY="$(REGISTRY)" TAG="$(TAG)" bash -c 'source scripts/run_service.sh up'

deploy-down:
	@REGISTRY="$(REGISTRY)" TAG="$(TAG)" bash -c 'source scripts/run_service.sh down'

test:
	@uv sync --extra dev --extra geti
	@uv run pytest tests/ \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html:coverage \
		--cov-branch || true

clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf .pytest_cache htmlcov coverage coverage.xml .coverage \
		$(TOOLS_DIR) security-results bandit-venv .pylintrc .venv

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
	@uv sync --extra dev
	@( \
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
	uv run pylint --rcfile=.pylintrc src/ \
		> security-results/pylint-report-$(SERVICE_NAME).json 2>/dev/null || true && \
	rm -f .pylintrc
	@echo "Report: security-results/pylint-report-$(SERVICE_NAME).json"

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
	trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format json \
		--output security-results/trivy-fs-$(SERVICE_NAME).json .; \
	trivy fs --format spdx-json \
		--output security-results/trivy-fs-$(SERVICE_NAME).spdx.json .; \
	if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
		trivy fs --severity HIGH,CRITICAL --ignore-unfixed --format template \
			--template "@$$TRIVY_HTML_TPL" \
			--output security-results/trivy-fs-$(SERVICE_NAME).html .; \
	fi
	@echo "Filesystem scan complete: security-results/trivy-fs-$(SERVICE_NAME)*.{json,spdx.json,html}"

trivy-scan-image: build
	@echo "Running Trivy Image Scan..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	if [ -z "$$(docker images -q $(REGISTRY)$(SERVICE_NAME):$(TAG) 2>/dev/null)" ]; then \
		echo "Image '$(REGISTRY)$(SERVICE_NAME):$(TAG)' not found, skipping."; \
	else \
		trivy image --severity HIGH,CRITICAL --ignore-unfixed --format json \
			--output security-results/trivy-image-$(SERVICE_NAME).json \
			$(REGISTRY)$(SERVICE_NAME):$(TAG); \
		trivy image --format spdx-json \
			--output security-results/trivy-image-$(SERVICE_NAME).spdx.json \
			$(REGISTRY)$(SERVICE_NAME):$(TAG); \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy image --severity HIGH,CRITICAL --ignore-unfixed --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-image-$(SERVICE_NAME).html \
				$(REGISTRY)$(SERVICE_NAME):$(TAG); \
		fi; \
	fi
	@echo "Image scan complete: security-results/trivy-image-$(SERVICE_NAME)*.{json,spdx.json,html}"

trivy-scan-config:
	@echo "Running Trivy Config Scan..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME).json \
		--file-patterns "dockerfile:Dockerfile" docker; \
	if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
		trivy config --severity HIGH,CRITICAL --format template \
			--template "@$$TRIVY_HTML_TPL" \
			--output security-results/trivy-config-$(SERVICE_NAME).html \
			--file-patterns "dockerfile:Dockerfile" docker; \
	fi
	@echo "Config scan complete: security-results/trivy-config-$(SERVICE_NAME)*.{json,html}"

clamav-scan:
	@echo "Running ClamAV Antivirus Scan..."
	@mkdir -p security-results
	@clamscan -r . \
		--exclude-dir=.git \
		--exclude-dir=.venv \
		--exclude-dir=coverage \
		--exclude-dir=security-results \
		--exclude-dir=chart \
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
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r src/ \
		-f txt -o security-results/bandit-report-$(SERVICE_NAME).txt || true && \
	echo "Generating JSON Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r src/ \
		-f json -o security-results/bandit-report-$(SERVICE_NAME).json || true && \
	echo "Generating HTML Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low -r src/ \
		-f html -o security-results/bandit-report-$(SERVICE_NAME).html || true && \
	deactivate && \
	rm -rf bandit-venv
	@echo "Bandit scan complete. Check security-results/ for txt, json, and html reports."

# Resolves a usable `gitleaks` binary, auto-installing a local copy under
# $(TOOLS_DIR) (no sudo/PATH changes) if it isn't already available.
define ENSURE_GITLEAKS
	if command -v gitleaks >/dev/null 2>&1; then \
		GITLEAKS_BIN="$$(command -v gitleaks)"; \
	elif [ -x "$(TOOLS_DIR)/gitleaks" ]; then \
		GITLEAKS_BIN="$(TOOLS_DIR)/gitleaks"; \
	else \
		echo "  → gitleaks not found, installing v$(GITLEAKS_VERSION) locally into $(TOOLS_DIR)/..."; \
		mkdir -p $(TOOLS_DIR); \
		OS=$$(uname -s | tr '[:upper:]' '[:lower:]'); \
		ARCH=$$(uname -m); \
		case "$$ARCH" in \
			x86_64) ARCH=x64 ;; \
			aarch64|arm64) ARCH=arm64 ;; \
			*) echo "Unsupported architecture '$$ARCH' for gitleaks auto-install."; \
			   echo "Install manually: https://github.com/gitleaks/gitleaks/releases"; exit 1 ;; \
		esac; \
		curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v$(GITLEAKS_VERSION)/gitleaks_$(GITLEAKS_VERSION)_$${OS}_$${ARCH}.tar.gz" \
			-o $(TOOLS_DIR)/gitleaks.tar.gz; \
		tar -xzf $(TOOLS_DIR)/gitleaks.tar.gz -C $(TOOLS_DIR) gitleaks; \
		chmod +x $(TOOLS_DIR)/gitleaks; \
		rm -f $(TOOLS_DIR)/gitleaks.tar.gz; \
		GITLEAKS_BIN="$(TOOLS_DIR)/gitleaks"; \
	fi
endef

gitleaks-scan:
	@echo "Running Gitleaks Secrets Scan..."
	@mkdir -p security-results
	@$(ENSURE_GITLEAKS); \
	echo "→ Using gitleaks: $$GITLEAKS_BIN ($$($$GITLEAKS_BIN version 2>/dev/null))"; \
	$$GITLEAKS_BIN dir . -v \
		-r security-results/gitleaks-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).json || true
	@echo "Gitleaks scan complete: security-results/gitleaks-*"

# Resolves a usable `codeql` binary, auto-installing a local copy under
# $(TOOLS_DIR) (no sudo/PATH changes) if it isn't already available.
define ENSURE_CODEQL
	if command -v codeql >/dev/null 2>&1; then \
		CODEQL_BIN="$$(command -v codeql)"; \
	elif [ -x "$(TOOLS_DIR)/codeql/codeql" ]; then \
		CODEQL_BIN="$(TOOLS_DIR)/codeql/codeql"; \
	else \
		if ! command -v unzip >/dev/null 2>&1; then \
			echo "unzip is required to auto-install the CodeQL CLI but was not found."; \
			echo "Install unzip, or install CodeQL manually: https://github.com/github/codeql-cli-binaries/releases"; \
			exit 1; \
		fi; \
		OS=$$(uname -s); \
		case "$$OS" in \
			Linux) PLATFORM=linux64 ;; \
			Darwin) PLATFORM=osx64 ;; \
			*) echo "Unsupported OS '$$OS' for CodeQL auto-install."; \
			   echo "Install manually: https://github.com/github/codeql-cli-binaries/releases"; exit 1 ;; \
		esac; \
		echo "  → CodeQL CLI not found, installing $(CODEQL_VERSION) locally into $(TOOLS_DIR)/codeql/..."; \
		mkdir -p $(TOOLS_DIR); \
		curl -sSfL "https://github.com/github/codeql-cli-binaries/releases/download/$(CODEQL_VERSION)/codeql-$${PLATFORM}.zip" \
			-o $(TOOLS_DIR)/codeql.zip; \
		unzip -q -o $(TOOLS_DIR)/codeql.zip -d $(TOOLS_DIR); \
		rm -f $(TOOLS_DIR)/codeql.zip; \
		CODEQL_BIN="$(TOOLS_DIR)/codeql/codeql"; \
	fi
endef

codeql-scan:
	@echo "Running CodeQL Security Analysis..."
	@mkdir -p security-results
	@$(ENSURE_CODEQL); \
	echo "→ Using CodeQL: $$CODEQL_BIN ($$($$CODEQL_BIN version --format=terse 2>/dev/null))"; \
	echo "→ Checking CodeQL Python query pack..."; \
	if ! $$CODEQL_BIN resolve qlpacks 2>/dev/null | grep -q 'codeql/python-queries'; then \
		echo "Downloading codeql/python-queries..."; \
		$$CODEQL_BIN pack download codeql/python-queries; \
	else \
		echo "codeql/python-queries already available."; \
	fi; \
	echo "→ Creating CodeQL database for Python (src)..."; \
	$$CODEQL_BIN database create security-results/codeql-db-python-$(SERVICE_NAME) \
		--language=python \
		--source-root=src \
		--build-mode=none \
		--overwrite 2>&1 | tail -5; \
	echo "→ Running CodeQL analysis (SARIF)..."; \
	$$CODEQL_BIN database analyze security-results/codeql-db-python-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-python-$(SERVICE_NAME).sarif || true; \
	echo "→ Running CodeQL analysis (CSV)..."; \
	$$CODEQL_BIN database analyze security-results/codeql-db-python-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=csv \
		--output=security-results/codeql-python-$(SERVICE_NAME).csv || true; \
	echo "CodeQL scan complete: security-results/codeql-*.{sarif,csv}"
