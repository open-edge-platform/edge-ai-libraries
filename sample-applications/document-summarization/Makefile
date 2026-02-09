# SPDX-FileCopyrightText: Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Document Summarization - Makefile
# ==============================================================================
#
# Build, test, deploy, and manage the Document Summarization application.
# Supports OVMS model server with CPU deployment mode.
#
# Quick Start:
#   make help          - Show all available commands
#   make build         - Build all Docker images
#   make deploy        - Deploy using pre-built images
#   make deploy-build  - Build and deploy
#   make undeploy      - Stop the application
#
# Configuration:
#   DEVICE                      - CPU (default)
#   LLM_MODEL                   - LLM model name (default: microsoft/Phi-3.5-mini-instruct)
#   VOLUME_OVMS                 - Path to OVMS model volume (required)
#   REGISTRY                    - Image registry (default: intel/)
#   TAG                         - Image tag (default: 1.0.3)
#
# ==============================================================================

SHELL := bash -eu -o pipefail
.DEFAULT_GOAL := help

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := document-summary
VERSION ?= latest
PYTHON_VERSION := 3.11

# ==============================================================================
# Pre-built Image Configuration
# ==============================================================================

DEFAULT_REGISTRY := intel/
DEFAULT_TAG := 1.0.3

# ==============================================================================
# Model Configuration
# ==============================================================================

LLM_MODEL ?= microsoft/Phi-3.5-mini-instruct

# ==============================================================================
# OVMS Configuration
# ==============================================================================

WEIGHT_FORMAT ?= int8
TARGET_DEVICE ?= CPU

# ==============================================================================
# OpenTelemetry Configuration (Optional)
# ==============================================================================

OTEL_SERVICE_NAME ?= document-summarization
OTEL_SERVICE_ENV ?= development
OTEL_SERVICE_VERSION ?= 1.0.0

# ==============================================================================
# Component Configuration
# ==============================================================================

COMPONENTS := app
TEST_COMPONENTS := app

app_CONTEXT_DIR := ./
app_DOCKERFILE := ./Dockerfile

# ==============================================================================
# Deployment Configuration
# ==============================================================================

DEVICE ?= CPU
REGISTRY ?= $(DEFAULT_REGISTRY)
TAG ?= $(DEFAULT_TAG)
VOLUME_OVMS ?= $(shell pwd)

DEVICE_UPPER := $(shell echo $(DEVICE) | tr '[:lower:]' '[:upper:]')

# ============================================================================== 
# Internal Variables
# ============================================================================== 

TEST_TARGETS := $(addprefix test-,$(TEST_COMPONENTS))

.PHONY: all build test clean help list deploy deploy-build undeploy \
        shellcheck pylint \
        trivy-scan trivy-scan-fs trivy-scan-image trivy-scan-config \
        clamav-scan bandit-scan gitleaks-scan \
        $(TEST_TARGETS) \
        get-service-name get-component-names get-image-tags get-context-dirs \
        get-python-version get-scan-matrix-json

# ============================================================================== 
# Build Targets
# ============================================================================== 

build:
	@echo "📦 Building all components..."
	@$(foreach component,$(COMPONENTS), \
		echo "Building $(component): $(SERVICE_NAME):$(VERSION)"; \
		docker build \
			-t $(SERVICE_NAME):$(VERSION) \
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


test-app:
	@echo "══════════════════════════════════════════════════"
	@echo "🧪 Test - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Configuration:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo "  WEIGHT_FORMAT:    $(WEIGHT_FORMAT)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo ""
	@echo "Storage:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ -z "$${VOLUME_OVMS:-}" ]; then \
		echo "  VOLUME_OVMS:      $(VOLUME_OVMS) (default)"; \
	else \
		echo "  VOLUME_OVMS:      $${VOLUME_OVMS}"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(DEVICE_UPPER)" != "CPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 1; \
	fi; \
	read -p "Proceed with testing? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		echo ""; \
		echo "Testing cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Setting up environment and running tests..."; \
		python3 -m venv docsum-venv && \
		source docsum-venv/bin/activate && \
		pip install poetry && \
		poetry install --with dev && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export WEIGHT_FORMAT="$(WEIGHT_FORMAT)" && \
		export VOLUME_OVMS="$${VOLUME_OVMS:-$(VOLUME_OVMS)}" && \
		poetry run pytest tests/unit_tests/ \
			--verbose \
			--cov=app \
			--cov-report=term-missing \
			--cov-branch && \
		deactivate && \
		rm -rf docsum-venv; \
		echo ""; \
		echo "✅ Tests completed!"; \
	fi

# ============================================================================== 
# Deployment Targets
# ============================================================================== 

deploy:
	@echo "══════════════════════════════════════════════════"
	@echo "🚀 Deploy - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Configuration:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo "  WEIGHT_FORMAT:    $(WEIGHT_FORMAT)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo ""
	@echo "Storage:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@if [ -z "$${VOLUME_OVMS:-}" ]; then \
		echo "  VOLUME_OVMS:      $(VOLUME_OVMS) (default)"; \
	else \
		echo "  VOLUME_OVMS:      $${VOLUME_OVMS}"; \
	fi
	@echo ""
	@echo "Images:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  REGISTRY:         $${REGISTRY:-$(DEFAULT_REGISTRY)}"
	@echo "  TAG:              $${TAG:-$(DEFAULT_TAG)}"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(DEVICE_UPPER)" != "CPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 1; \
	fi; \
	read -p "Proceed with deployment? [y/N]: " confirm; \
	if [ "$${confirm}" != "y" ] && [ "$${confirm}" != "Y" ]; then \
		echo ""; \
		echo "Deployment cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Deploying..."; \
		export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}" && \
		export TAG="$${TAG:-$(DEFAULT_TAG)}" && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export VOLUME_OVMS="$${VOLUME_OVMS:-$(VOLUME_OVMS)}" && \
		export OTLP_ENDPOINT="$${OTLP_ENDPOINT:-}" && \
		source setup.sh && \
		docker compose up -d; \
		echo ""; \
		echo "✅ Deployment complete!"; \
	fi

deploy-build:
	@echo "══════════════════════════════════════════════════"
	@echo "🚀 Deploy Build - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Configuration:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(DEVICE_UPPER)" != "CPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 1; \
	fi; \
	read -p "Proceed with deployment? [y/N]: " confirm; \
	if [ "$${confirm}" != "y" ] && [ "$${confirm}" != "Y" ]; then \
		echo ""; \
		echo "Deployment cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Building and deploying..."; \
		$(MAKE) build && \
		export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}" && \
		export TAG="$${TAG:-$(DEFAULT_TAG)}" && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export VOLUME_OVMS="$${VOLUME_OVMS:-$(VOLUME_OVMS)}" && \
		export OTLP_ENDPOINT="$${OTLP_ENDPOINT:-}" && \
		source setup.sh && \
		docker compose up -d; \
		echo ""; \
		echo "✅ Deployment complete!"; \
	fi

undeploy:
	@echo "══════════════════════════════════════════════════"
	@echo "🛑 Stopping $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@docker compose down
	@echo "✅ Application stopped."

# ============================================================================== 
# Code Quality Targets
# ============================================================================== 

shellcheck:
	@echo "🔍 Running ShellCheck..."
	@mkdir -p security-results
	@echo "=== ShellCheck Report ===" > security-results/shellcheck-report-$(SERVICE_NAME).txt
	@echo "Date: $$(date)" >> security-results/shellcheck-report-$(SERVICE_NAME).txt
	@echo "" >> security-results/shellcheck-report-$(SERVICE_NAME).txt
	@find . -type f \( -name "*.sh" -o -name "*.bash" \) -print0 | while IFS= read -r -d '' file; do \
		echo "Checking: $$file" >> security-results/shellcheck-report-$(SERVICE_NAME).txt; \
		shellcheck "$$file" >> security-results/shellcheck-report-$(SERVICE_NAME).txt 2>&1 || true; \
		echo "---" >> security-results/shellcheck-report-$(SERVICE_NAME).txt; \
	done
	@echo "✅ Report: security-results/shellcheck-report-$(SERVICE_NAME).txt"

pylint:
	@echo "🔍 Running Pylint..."
	@python3 -m venv pylint-venv && \
	source pylint-venv/bin/activate && \
	pip install poetry && \
	poetry install --no-root --with dev && \
	poetry add --group dev pylint && \
	mkdir -p security-results && \
	echo "=== Pylint Report ===" > security-results/pylint-report-$(SERVICE_NAME).txt && \
	echo "Date: $$(date)" >> security-results/pylint-report-$(SERVICE_NAME).txt && \
	echo "" >> security-results/pylint-report-$(SERVICE_NAME).txt && \
	( \
		echo "[MESSAGES CONTROL]"; \
		echo "disable=C0111,C0103,R0903,R0913,W0613,W0622,R0801,R0902,R0914,R0915,R0912,C0301,C0302"; \
		echo ""; \
		echo "[FORMAT]"; \
		echo "max-line-length=120"; \
		echo ""; \
		echo "[REPORTS]"; \
		echo "output-format=text"; \
		echo "reports=yes"; \
	) > .pylintrc && \
	find app/ -type f -name "*.py" -exec poetry run pylint --rcfile=.pylintrc {} + \
		>> security-results/pylint-report-$(SERVICE_NAME).txt 2>&1 || true && \
	deactivate && \
	rm -rf pylint-venv .pylintrc
	@echo "✅ Report: security-results/pylint-report-$(SERVICE_NAME).txt"

# ============================================================================== 
# Security Scanning
# ============================================================================== 

trivy-scan: trivy-scan-fs trivy-scan-image trivy-scan-config
	@echo "📦 Creating security scan archive..."
	@cd security-results && zip -r trivy-scan-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).zip trivy-* 2>/dev/null || true
	@echo "✅ All Trivy scans complete. Reports: security-results/trivy-*"

trivy-scan-fs:
	@echo "🔍 Running Trivy Filesystem Scan..."
	@mkdir -p security-results
	@trivy fs --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-fs-$(SERVICE_NAME).json . || true
	@trivy fs --severity HIGH,CRITICAL --format table \
		--output security-results/trivy-fs-$(SERVICE_NAME).txt . || true
	@echo "✅ Filesystem scan complete: security-results/trivy-fs-$(SERVICE_NAME).*"

trivy-scan-image:
	@echo "🔍 Running Trivy Image Scans..."
	@mkdir -p security-results
	@echo "Scanning app image..."
	@IMAGE="$(SERVICE_NAME):$(VERSION)"; \
	if [ -z "$$(docker images -q $$IMAGE 2>/dev/null)" ]; then \
		echo "⚠️  Image '$$IMAGE' not found. Run 'make build' first."; \
	else \
		trivy image --severity HIGH,CRITICAL --format table \
			--output security-results/trivy-image-$(SERVICE_NAME).txt \
			$$IMAGE || true; \
		trivy image --severity HIGH,CRITICAL --format spdx-json --scanners vuln \
			--output security-results/trivy-image-$(SERVICE_NAME)-spdx.json \
			$$IMAGE || true; \
	fi
	@echo "✅ Image scans complete: security-results/trivy-image-*"

trivy-scan-config:
	@echo "🔍 Running Trivy Config Scans..."
	@mkdir -p security-results
	@trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME).json \
		--file-patterns "dockerfile:Dockerfile" . || true
	@echo "✅ Config scans complete: security-results/trivy-config-*"

clamav-scan:
	@echo "🦠 Running ClamAV Antivirus Scan..."
	@mkdir -p security-results
	@clamscan -r . \
		--exclude-dir=.git \
		--exclude-dir=node_modules \
		--exclude-dir=venv \
		--exclude-dir=ui/test \
		--exclude-dir=tests \
		> security-results/clamav-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).txt 2>&1 || true
	@echo "✅ ClamAV scan complete: security-results/clamav-*"

bandit-scan:
	@echo "🔐 Running Bandit Security Scan..."
	@mkdir -p security-results
	@python3 -m venv bandit-venv && \
	source bandit-venv/bin/activate && \
	pip install bandit && \
	bandit -r . \
		--exclude .git,node_modules,venv,ui/test,tests \
		-f txt \
		-o security-results/bandit-report-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).txt || true && \
	deactivate && \
	rm -rf bandit-venv
	@echo "✅ Bandit scan complete: security-results/bandit-report-*"

gitleaks-scan:
	@echo "🔑 Running Gitleaks Secrets Scan..."
	@mkdir -p security-results
	@gitleaks dir . -v \
		-r security-results/gitleaks-$(SERVICE_NAME)-$$(date +%Y%m%d-%H%M%S).json || true
	@echo "✅ Gitleaks scan complete: security-results/gitleaks-*"

# ============================================================================== 
# Utility Targets
# ============================================================================== 

list:
	@echo "══════════════════════════════════════════════════"
	@echo "📋 Build Configuration: $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Version: $(VERSION)"
	@echo ""
	@echo "Components:"
	@$(foreach component,$(COMPONENTS), echo "  • $(component) → $(SERVICE_NAME):$(VERSION)";)
	@echo ""
	@echo "Test Components:"
	@$(foreach component,$(TEST_COMPONENTS), echo "  • $(component)";)

clean:
	@echo "🧹 Removing Docker images..."
	@$(foreach component,$(COMPONENTS), \
		docker rmi -f $(SERVICE_NAME):$(VERSION) 2>/dev/null || true; \
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
	@$(foreach component,$(COMPONENTS), echo "$(SERVICE_NAME):$(VERSION)";)

get-context-dirs:
	@$(foreach component,$(COMPONENTS), echo "$($(component)_CONTEXT_DIR)";)

get-python-version:
	@echo $(PYTHON_VERSION)

get-scan-matrix-json:
	@printf '{"include":['
	@$(foreach component,$(COMPONENTS), \
		$(eval COMMA := $(if $(findstring $(component),$(firstword $(COMPONENTS))),,',')) \
		printf '%s' '$(COMMA){"name":"$(component)","image":"$(SERVICE_NAME):$(VERSION)","context":"$($(component)_CONTEXT_DIR)","dockerfile":"$($(component)_DOCKERFILE)"}'; \
	)
	@printf ']}\n'

# ============================================================================== 
# Help
# ============================================================================== 

help:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════╗"
	@echo "║              Document Summarization - Makefile                   ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "BUILD & TEST"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  build            Build all Docker images"
	@echo "  test             Run all unit tests"
	@echo "  test-app         Run app tests"
	@echo ""
	@echo "DEPLOYMENT"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  deploy           Deploy using pre-built images"
	@echo "  deploy-build     Build images and deploy"
	@echo "  undeploy         Stop and remove containers"
	@echo ""
	@echo "  Environment Variables:"
	@echo "    VOLUME_OVMS                 Path to OVMS model volume (default: $(VOLUME_OVMS))"
	@echo "    LLM_MODEL                   LLM model (default: $(LLM_MODEL))"
	@echo "    DEVICE                      CPU (default)"
	@echo "    REGISTRY                    Image registry (default: $(DEFAULT_REGISTRY))"
	@echo "    TAG                         Image tag (default: $(DEFAULT_TAG))"
	@echo "    OTLP_ENDPOINT               OpenTelemetry endpoint (optional)"
	@echo ""
	@echo "CODE QUALITY & SECURITY"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  shellcheck       Run ShellCheck on shell scripts"
	@echo "  pylint           Run Pylint on Python code"
	@echo "  trivy-scan       Run all Trivy scans"
	@echo "  trivy-scan-fs    Run Trivy filesystem scan"
	@echo "  trivy-scan-image Run Trivy image scans"
	@echo "  trivy-scan-config Run Trivy Dockerfile scans"
	@echo "  clamav-scan      Run ClamAV antivirus scan"
	@echo "  bandit-scan      Run Bandit security scan"
	@echo "  gitleaks-scan    Run Gitleaks secrets scan"
	@echo ""
	@echo "UTILITIES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  list             Show build configuration"
	@echo "  clean            Remove built Docker images"
	@echo "  help             Show this help message"
	@echo ""
	@echo "EXAMPLES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  # Deploy with default settings"
	@echo "  export VOLUME_OVMS=\$$PWD"
	@echo "  export LLM_MODEL=microsoft/Phi-3.5-mini-instruct"
	@echo "  make deploy"
	@echo ""
	@echo "  # Build and deploy"
	@echo "  export VOLUME_OVMS=\$$PWD"
	@echo "  make deploy-build"
	@echo ""
	@echo "  # Run app tests"
	@echo "  make test-app"
	@echo ""

