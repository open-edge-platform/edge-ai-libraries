# SPDX-FileCopyrightText: Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Chat Question & Answer - Makefile
# ==============================================================================
#
# Build, test, deploy, and manage the Chat Q&A application.
# Supports OVMS model server with CPU/GPU deployment modes.
# Note: VLLM and TGI are deprecated and no longer supported.
#
# Quick Start:
#   make help          - Show all available commands
#   make build         - Build all Docker images
#   make deploy        - Deploy using pre-built images
#   make deploy-build  - Build and deploy
#   make undeploy      - Stop the application
#
# Configuration:
#   LLM_SERVER                  - OVMS (default). VLLM/TGI deprecated.
#   EMBED_SERVER                - TEI (default) or OVMS
#   DEVICE                      - CPU (default) or GPU
#   HUGGINGFACEHUB_API_TOKEN    - Required for model access
#   LLM_MODEL                   - LLM model name (default: Qwen/Qwen2.5-7B-Instruct)
#   EMBEDDING_MODEL_NAME        - Embedding model (default: Alibaba-NLP/gte-large-en-v1.5)
#   RERANKER_MODEL              - Reranker model (default: BAAI/bge-reranker-base)
#
# ==============================================================================

SHELL := bash -eu -o pipefail
.DEFAULT_GOAL := help

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := chatqna
VERSION ?= latest
PYTHON_VERSION := 3.12
NODE_VERSION := 22

# ==============================================================================
# Pre-built Image Configuration
# ==============================================================================

DEFAULT_REGISTRY := intel/

# Chat Q&A image tags
DEFAULT_TAG := 2.0.1
DEFAULT_UI_TAG := $(DEFAULT_TAG)
DEFAULT_BACKEND_TAG := $(DEFAULT_TAG)
DEFAULT_DOCUMENT_INGESTION_TAG := 1.2.3

# Core image tags (shared with chat-question-and-answer-core)
DEFAULT_CORE_TAG := core_1.3.1
DEFAULT_CORE_GPU_TAG := core_gpu_1.3.1
DEFAULT_CORE_OLLAMA_TAG := core_ollama_1.3.1

# ==============================================================================
# Model Configuration
# ==============================================================================

LLM_MODEL ?= Qwen/Qwen2.5-7B-Instruct
EMBEDDING_MODEL_NAME ?= Alibaba-NLP/gte-large-en-v1.5
RERANKER_MODEL ?= BAAI/bge-reranker-base

# ==============================================================================
# Component Configuration
# ==============================================================================

COMPONENTS := frontend backend
TEST_COMPONENTS := frontend backend

frontend_CONTEXT_DIR := ./ui/react/
frontend_DOCKERFILE := ./ui/react/Dockerfile

backend_CONTEXT_DIR := ./
backend_DOCKERFILE := ./Dockerfile

# ==============================================================================
# Deployment Configuration
# ==============================================================================

DEVICE ?= CPU
LLM_SERVER ?= OVMS
EMBED_SERVER ?= TEI
REGISTRY ?= $(DEFAULT_REGISTRY)
UI_TAG ?= $(DEFAULT_UI_TAG)
BACKEND_TAG ?= $(DEFAULT_BACKEND_TAG)

DEVICE_UPPER := $(shell echo $(DEVICE) | tr '[:lower:]' '[:upper:]')
LLM_SERVER_UPPER := $(shell echo $(LLM_SERVER) | tr '[:lower:]' '[:upper:]')
EMBED_SERVER_UPPER := $(shell echo $(EMBED_SERVER) | tr '[:lower:]' '[:upper:]')

# ==============================================================================
# Internal Variables
# ==============================================================================

TEST_TARGETS := $(addprefix test-,$(TEST_COMPONENTS))

.PHONY: all build test clean help list deploy deploy-build undeploy \
        shellcheck pylint \
        trivy-scan trivy-scan-fs trivy-scan-image trivy-scan-config \
        clamav-scan bandit-scan gitleaks-scan codeql-scan \
        $(TEST_TARGETS) \
        get-service-name get-component-names get-image-tags get-context-dirs \
        get-python-version get-node-version get-scan-matrix-json

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

test-frontend:
	@echo "🧪 Running frontend tests..."
	@cd $(frontend_CONTEXT_DIR) && npm install && npm run coverage

test-backend:
	@echo "══════════════════════════════════════════════════"
	@echo "🧪 Test Backend - $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Configuration:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_SERVER:       $(LLM_SERVER_UPPER)"
	@echo "  EMBED_SERVER:     $(EMBED_SERVER_UPPER)"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@echo "  EMBEDDING_MODEL:  $${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}"
	@echo "  RERANKER_MODEL:   $${RERANKER_MODEL:-$(RERANKER_MODEL)}"
	@echo ""
	@echo "Internal:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  REGISTRY:         $${REGISTRY:-$(DEFAULT_REGISTRY)}"
	@echo "  TAG:              $${TAG:-$(DEFAULT_TAG)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(LLM_SERVER_UPPER)" != "OVMS" ] && [ "$(LLM_SERVER_UPPER)" != "TGI" ] && [ "$(LLM_SERVER_UPPER)" != "VLLM" ]; then \
		echo "❌ Invalid LLM_SERVER '$(LLM_SERVER_UPPER)'. Use OVMS (recommended), TGI, or VLLM."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(EMBED_SERVER_UPPER)" != "TEI" ] && [ "$(EMBED_SERVER_UPPER)" != "OVMS" ]; then \
		echo "❌ Invalid EMBED_SERVER '$(EMBED_SERVER_UPPER)'. Use TEI or OVMS."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(DEVICE_UPPER)" != "CPU" ] && [ "$(DEVICE_UPPER)" != "GPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU or GPU."; \
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
		python3 -m venv chat-qna-venv && \
		source chat-qna-venv/bin/activate && \
		pip install poetry && \
		poetry install --with dev && \
		export HUGGINGFACEHUB_API_TOKEN="$${HUGGINGFACEHUB_API_TOKEN:-}" && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export EMBEDDING_MODEL_NAME="$${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}" && \
		export RERANKER_MODEL="$${RERANKER_MODEL:-$(RERANKER_MODEL)}" && \
		export OTLP_ENDPOINT="$${OTLP_ENDPOINT:-}" && \
		export OTLP_ENDPOINT_TRACE="$${OTLP_ENDPOINT_TRACE:-}" && \
		export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}" && \
		export TAG="$${TAG:-$(DEFAULT_TAG)}" && \
		source setup.sh llm=$(LLM_SERVER_UPPER) embed=$(EMBED_SERVER_UPPER) && \
		source chat-qna-venv/bin/activate && \
		poetry run pytest tests/unit_tests/ \
			--verbose \
			--cov=app \
			--cov-report=html:coverage-backend \
			--cov-report=xml:coverage-backend.xml \
			--cov-report=term-missing \
			--cov-branch && \
		deactivate && \
		rm -rf chat-qna-venv; \
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
	@echo "  LLM_SERVER:       $(LLM_SERVER_UPPER)"
	@echo "  EMBED_SERVER:     $(EMBED_SERVER_UPPER)"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@echo "  EMBEDDING_MODEL:  $${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}"
	@echo "  RERANKER_MODEL:   $${RERANKER_MODEL:-$(RERANKER_MODEL)}"
	@echo ""
	@echo "Images:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  REGISTRY:         $${REGISTRY:-$(DEFAULT_REGISTRY)}"
	@echo "  UI_TAG:           $${UI_TAG:-$(DEFAULT_UI_TAG)}"
	@echo "  BACKEND_TAG:      $${BACKEND_TAG:-$(DEFAULT_BACKEND_TAG)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(LLM_SERVER_UPPER)" != "OVMS" ] && [ "$(LLM_SERVER_UPPER)" != "TGI" ] && [ "$(LLM_SERVER_UPPER)" != "VLLM" ]; then \
		echo "❌ Invalid LLM_SERVER '$(LLM_SERVER_UPPER)'. Use OVMS (recommended), TGI, or VLLM."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(EMBED_SERVER_UPPER)" != "TEI" ] && [ "$(EMBED_SERVER_UPPER)" != "OVMS" ]; then \
		echo "❌ Invalid EMBED_SERVER '$(EMBED_SERVER_UPPER)'. Use TEI or OVMS."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(DEVICE_UPPER)" != "CPU" ] && [ "$(DEVICE_UPPER)" != "GPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU or GPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 1; \
	fi; \
	read -p "Proceed with deployment? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		echo ""; \
		echo "Deployment cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Deploying..."; \
		export HUGGINGFACEHUB_API_TOKEN="$${HUGGINGFACEHUB_API_TOKEN:-}" && \
		export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}" && \
		export TAG="$${TAG:-$(DEFAULT_TAG)}" && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export EMBEDDING_MODEL_NAME="$${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}" && \
		export RERANKER_MODEL="$${RERANKER_MODEL:-$(RERANKER_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export OTLP_ENDPOINT="$${OTLP_ENDPOINT:-}" && \
		export OTLP_ENDPOINT_TRACE="$${OTLP_ENDPOINT_TRACE:-}" && \
		source setup.sh llm=$(LLM_SERVER_UPPER) embed=$(EMBED_SERVER_UPPER) && \
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
	@echo "  LLM_SERVER:       $(LLM_SERVER_UPPER)"
	@echo "  EMBED_SERVER:     $(EMBED_SERVER_UPPER)"
	@echo "  DEVICE:           $(DEVICE_UPPER)"
	@echo ""
	@echo "Models:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  LLM_MODEL:        $${LLM_MODEL:-$(LLM_MODEL)}"
	@echo "  EMBEDDING_MODEL:  $${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}"
	@echo "  RERANKER_MODEL:   $${RERANKER_MODEL:-$(RERANKER_MODEL)}"
	@if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "  HF_TOKEN:         ⚠️  Not Set (Required for gated models)"; \
	else \
		echo "  HF_TOKEN:         ✅ Set"; \
	fi
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@VALIDATION_ERROR=""; \
	if [ "$(LLM_SERVER_UPPER)" != "OVMS" ] && [ "$(LLM_SERVER_UPPER)" != "TGI" ] && [ "$(LLM_SERVER_UPPER)" != "VLLM" ]; then \
		echo "❌ Invalid LLM_SERVER '$(LLM_SERVER_UPPER)'. Use OVMS (recommended), TGI, or VLLM."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(EMBED_SERVER_UPPER)" != "TEI" ] && [ "$(EMBED_SERVER_UPPER)" != "OVMS" ]; then \
		echo "❌ Invalid EMBED_SERVER '$(EMBED_SERVER_UPPER)'. Use TEI or OVMS."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(DEVICE_UPPER)" != "CPU" ] && [ "$(DEVICE_UPPER)" != "GPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU or GPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 1; \
	fi; \
	read -p "Proceed with deployment? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		echo ""; \
		echo "Deployment cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Building and deploying..."; \
		export HUGGINGFACEHUB_API_TOKEN="$${HUGGINGFACEHUB_API_TOKEN:-}" && \
		export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}" && \
		export TAG="$${TAG:-$(DEFAULT_TAG)}" && \
		export LLM_MODEL="$${LLM_MODEL:-$(LLM_MODEL)}" && \
		export EMBEDDING_MODEL_NAME="$${EMBEDDING_MODEL_NAME:-$(EMBEDDING_MODEL_NAME)}" && \
		export RERANKER_MODEL="$${RERANKER_MODEL:-$(RERANKER_MODEL)}" && \
		export DEVICE="$(DEVICE_UPPER)" && \
		export OTLP_ENDPOINT="$${OTLP_ENDPOINT:-}" && \
		export OTLP_ENDPOINT_TRACE="$${OTLP_ENDPOINT_TRACE:-}" && \
		bash -c "source setup.sh llm=$(LLM_SERVER_UPPER) embed=$(EMBED_SERVER_UPPER) && docker compose up -d --build"; \
		echo ""; \
		echo "✅ Deployment complete!"; \
	fi

undeploy:
	@echo "══════════════════════════════════════════════════"
	@echo "🛑 Stopping $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@export HUGGINGFACEHUB_API_TOKEN='$${HUGGINGFACEHUB_API_TOKEN:-dummy}' && \
		export MINIO_ROOT_USER='$${MINIO_ROOT_USER:-dummy}' && \
		export MINIO_ROOT_PASSWORD='$${MINIO_ROOT_PASSWORD:-dummy}' && \
		export COMPOSE_PROFILES='OVMS,TEI,GPU-OVMS' && \
		(docker compose --profile OVMS --profile TEI --profile GPU-OVMS down 2>/dev/null || \
		docker compose down)
	@echo "✅ Application stopped."

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
	@python3 -m venv pylint-venv && \
	source pylint-venv/bin/activate && \
	pip install poetry && \
	if ! command -v pg_config >/dev/null 2>&1; then \
		echo "→ Installing psycopg-binary (libpq-dev not found)..."; \
		pip install "psycopg[binary]>=3.2.3"; \
	fi && \
	poetry install --no-root --with dev 2>&1 | grep -v "psycopg-c" && \
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
		echo "output-format=json"; \
		echo "reports=yes"; \
	) > .pylintrc && \
	find app/ -type f -name "*.py" -exec poetry run pylint --rcfile=.pylintrc {} + \
		> security-results/pylint-report-$(SERVICE_NAME).json 2>/dev/null || true && \
	deactivate && \
	rm -rf pylint-venv .pylintrc
	@echo "✅ Report: security-results/pylint-report-$(SERVICE_NAME).json"

# ==============================================================================
# Security Scanning
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
	echo "Scanning backend image..."; \
	if [ -z "$$(docker images -q $(SERVICE_NAME)-backend:$(VERSION) 2>/dev/null)" ]; then \
		echo "⚠️  Backend image '$(SERVICE_NAME)-backend:$(VERSION)' not found. Run 'make build' first."; \
	else \
		trivy image --severity HIGH,CRITICAL --ignore-unfixed --format json \
			--output security-results/trivy-image-$(SERVICE_NAME)-backend.json \
			$(SERVICE_NAME)-backend:$(VERSION) || true; \
		trivy image --format spdx-json \
			--output security-results/trivy-image-$(SERVICE_NAME)-backend.spdx.json \
			$(SERVICE_NAME)-backend:$(VERSION) || true; \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy image --severity HIGH,CRITICAL --ignore-unfixed --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-image-$(SERVICE_NAME)-backend.html \
				$(SERVICE_NAME)-backend:$(VERSION) || true; \
		fi; \
	fi; \
	echo "Scanning frontend image..."; \
	if [ -z "$$(docker images -q $(SERVICE_NAME)-frontend:$(VERSION) 2>/dev/null)" ]; then \
		echo "⚠️  Frontend image '$(SERVICE_NAME)-frontend:$(VERSION)' not found. Run 'make build' first."; \
	else \
		trivy image --severity HIGH,CRITICAL --ignore-unfixed --format json \
			--output security-results/trivy-image-$(SERVICE_NAME)-frontend.json \
			$(SERVICE_NAME)-frontend:$(VERSION) || true; \
		trivy image --format spdx-json \
			--output security-results/trivy-image-$(SERVICE_NAME)-frontend.spdx.json \
			$(SERVICE_NAME)-frontend:$(VERSION) || true; \
		if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
			trivy image --severity HIGH,CRITICAL --ignore-unfixed --format template \
				--template "@$$TRIVY_HTML_TPL" \
				--output security-results/trivy-image-$(SERVICE_NAME)-frontend.html \
				$(SERVICE_NAME)-frontend:$(VERSION) || true; \
		fi; \
	fi
	@echo "✅ Image scans complete: security-results/trivy-image-*.{json,spdx.json,html}"

trivy-scan-config:
	@echo "🔍 Running Trivy Config Scans..."
	@mkdir -p security-results
	@$(ENSURE_TRIVY_HTML_TPL); \
	trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME)-backend.json \
		--file-patterns "dockerfile:Dockerfile" . || true; \
	if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
		trivy config --severity HIGH,CRITICAL --format template \
			--template "@$$TRIVY_HTML_TPL" \
			--output security-results/trivy-config-$(SERVICE_NAME)-backend.html \
			--file-patterns "dockerfile:Dockerfile" . || true; \
	fi; \
	trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME)-frontend.json \
		--file-patterns "dockerfile:Dockerfile" ui/ || true; \
	if [ -n "$$TRIVY_HTML_TPL" ] && [ -f "$$TRIVY_HTML_TPL" ]; then \
		trivy config --severity HIGH,CRITICAL --format template \
			--template "@$$TRIVY_HTML_TPL" \
			--output security-results/trivy-config-$(SERVICE_NAME)-frontend.html \
			--file-patterns "dockerfile:Dockerfile" ui/ || true; \
	fi
	@echo "✅ Config scans complete: security-results/trivy-config-*.{json,html}"

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
	pip install --upgrade pip && \
	pip install bandit[toml] && \
	CONFIG_OPT=""; \
	if [ -f "pyproject.toml" ]; then CONFIG_OPT="-c pyproject.toml"; fi; \
	echo "📝 Generating TXT Report (matches CI)..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low \
		-r . --exclude .git,node_modules,venv,bandit-venv,ui \
		-f txt -o security-results/bandit-report-$(SERVICE_NAME).txt || true && \
	echo "📊 Generating JSON Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low \
		-r . --exclude .git,node_modules,venv,bandit-venv,ui \
		-f json -o security-results/bandit-report-$(SERVICE_NAME).json || true && \
	echo "🌐 Generating HTML Report..." && \
	bandit $$CONFIG_OPT --severity-level low --confidence-level low \
		-r . --exclude .git,node_modules,venv,bandit-venv,ui \
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

	@# --- Python: app/ (backend) ---
	@echo "→ Creating CodeQL database for Python (app/)..."
	@codeql database create security-results/codeql-db-python-app-$(SERVICE_NAME) \
		--language=python \
		--source-root=app \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on app/ (SARIF)..."
	@codeql database analyze security-results/codeql-db-python-app-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-python-app-$(SERVICE_NAME).sarif || true
	@echo "→ Running CodeQL analysis on app/ (CSV)..."
	@codeql database analyze security-results/codeql-db-python-app-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=csv \
		--output=security-results/codeql-python-app-$(SERVICE_NAME).csv || true
	@echo "✅ Python (app/) analysis complete."
	@echo ""

	@# --- Python: tests/ ---
	@echo "→ Creating CodeQL database for Python (tests/)..."
	@codeql database create security-results/codeql-db-python-tests-$(SERVICE_NAME) \
		--language=python \
		--source-root=tests \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on tests/ (SARIF)..."
	@codeql database analyze security-results/codeql-db-python-tests-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-python-tests-$(SERVICE_NAME).sarif || true
	@echo "→ Running CodeQL analysis on tests/ (CSV)..."
	@codeql database analyze security-results/codeql-db-python-tests-$(SERVICE_NAME) \
		codeql/python-queries \
		--format=csv \
		--output=security-results/codeql-python-tests-$(SERVICE_NAME).csv || true
	@echo "✅ Python (tests/) analysis complete."
	@echo ""

	@# --- JavaScript/TypeScript: frontend ---
	@echo "→ Creating CodeQL database for JavaScript/TypeScript (frontend)..."
	@codeql database create security-results/codeql-db-javascript-$(SERVICE_NAME) \
		--language=javascript \
		--source-root=ui/react \
		--build-mode=none \
		--overwrite 2>&1 | tail -5

	@echo "→ Running CodeQL analysis on JavaScript/TypeScript (SARIF)..."
	@codeql database analyze security-results/codeql-db-javascript-$(SERVICE_NAME) \
		codeql/javascript-queries \
		--format=sarif-latest --sarif-add-snippets \
		--output=security-results/codeql-javascript-$(SERVICE_NAME).sarif || true
	@echo "→ Running CodeQL analysis on JavaScript/TypeScript (CSV)..."
	@codeql database analyze security-results/codeql-db-javascript-$(SERVICE_NAME) \
		codeql/javascript-queries \
		--format=csv \
		--output=security-results/codeql-javascript-$(SERVICE_NAME).csv || true
	@echo "✅ JavaScript/TypeScript analysis complete."
	@echo ""
	@echo "✅ CodeQL scan complete: security-results/codeql-*.{sarif,csv}"


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
	@$(foreach component,$(COMPONENTS), echo "  • $(component) → $(SERVICE_NAME)-$(component):$(VERSION)";)
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
	@echo "║            Chat Question & Answer - Makefile                     ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "BUILD & TEST"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  build            Build all Docker images"
	@echo "  test             Run all unit tests"
	@echo "  test-frontend    Run frontend tests"
	@echo "  test-backend     Run backend tests (uses LLM_SERVER/EMBED_SERVER env vars)"
	@echo ""
	@echo "DEPLOYMENT"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  deploy           Deploy using pre-built images"
	@echo "  deploy-build     Build images and deploy"
	@echo "  undeploy         Stop and remove containers"
	@echo ""
	@echo "  Environment Variables:"
	@echo "    LLM_SERVER                  OVMS (default). VLLM/TGI deprecated."
	@echo "    EMBED_SERVER                TEI (default) or OVMS"
	@echo "    DEVICE                      CPU (default) or GPU"
	@echo "    HUGGINGFACEHUB_API_TOKEN    Required for model access"
	@echo "    LLM_MODEL                   LLM model (default: $(LLM_MODEL))"
	@echo "    EMBEDDING_MODEL_NAME        Embedding model (default: $(EMBEDDING_MODEL_NAME))"
	@echo "    RERANKER_MODEL              Reranker model (default: $(RERANKER_MODEL))"
	@echo "    REGISTRY                    Image registry (default: $(DEFAULT_REGISTRY))"
	@echo "    UI_TAG                      UI image tag (default: $(DEFAULT_UI_TAG))"
	@echo "    BACKEND_TAG                 Backend image tag (default: $(DEFAULT_BACKEND_TAG))"
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
	@echo "  codeql-scan      Run CodeQL security analysis (Python + JavaScript)"
	@echo ""
	@echo "UTILITIES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  list             Show build configuration"
	@echo "  clean            Remove built Docker images"
	@echo "  help             Show this help message"
	@echo ""
	@echo "EXAMPLES"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  # Deploy with OVMS and TEI (default)"
	@echo "  export HUGGINGFACEHUB_API_TOKEN=<token>"
	@echo "  make deploy"
	@echo ""
	@echo "  # Deploy with GPU support"
	@echo "  export HUGGINGFACEHUB_API_TOKEN=<token>"
	@echo "  DEVICE=GPU make deploy"
	@echo ""
	@echo "  # Build and deploy with OVMS embedding"
	@echo "  export HUGGINGFACEHUB_API_TOKEN=<token>"
	@echo "  EMBED_SERVER=OVMS make deploy-build"
	@echo ""
	@echo "  # Run frontend tests"
	@echo "  make test-frontend"
	@echo ""

