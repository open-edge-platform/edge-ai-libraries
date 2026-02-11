# SPDX-FileCopyrightText: Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Chat Question & Answer Core - Makefile
# ==============================================================================
#
# Build, test, deploy, and manage the Chat Q&A application.
# Supports OpenVINO and Ollama backends with CPU/GPU deployment modes.
#
# Quick Start:
#   make help          - Show all available commands
#   make build         - Build all Docker images
#   make deploy        - Deploy using pre-built images
#   make deploy-build  - Build and deploy
#   make undeploy      - Stop the application
#
# Configuration:
#   BACKEND                    - OPENVINO (default) or OLLAMA
#   DEVICE                     - CPU (default) or GPU (OpenVINO only)
#   HUGGINGFACEHUB_API_TOKEN   - Required for OpenVINO backend
#
# ==============================================================================

SHELL := bash -eu -o pipefail
.DEFAULT_GOAL := help

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := chatqna-core
VERSION ?= latest
PYTHON_VERSION := 3.12
NODE_VERSION := 22

# ==============================================================================
# Pre-built Image Configuration
# ==============================================================================

DEFAULT_REGISTRY := intel/
DEFAULT_UI_TAG := core_1.3.0
DEFAULT_BACKEND_TAG := core_1.3.1
DEFAULT_GPU_TAG := core_gpu_1.3.1
DEFAULT_OLLAMA_TAG := core_ollama_1.3.1

# ==============================================================================
# Component Configuration
# ==============================================================================

COMPONENTS := frontend backend
TEST_COMPONENTS := frontend backend

frontend_CONTEXT_DIR := ./ui/
frontend_DOCKERFILE := ./ui/Dockerfile

backend_CONTEXT_DIR := ./
backend_DOCKERFILE := ./docker/Dockerfile

# ==============================================================================
# Deployment Configuration
# ==============================================================================

DEVICE ?= CPU
BACKEND ?= OPENVINO
REGISTRY ?= $(DEFAULT_REGISTRY)
UI_TAG ?= $(DEFAULT_UI_TAG)

DEVICE_UPPER := $(shell echo $(DEVICE) | tr '[:lower:]' '[:upper:]')
BACKEND_UPPER := $(shell echo $(BACKEND) | tr '[:lower:]' '[:upper:]')

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
	@echo "🧪 Running backend tests ($(BACKEND_UPPER))..."
	@python3 -m venv chat-qna-core-venv && \
	source chat-qna-core-venv/bin/activate && \
	pip install poetry && \
	poetry install --no-root --with dev && \
	export HUGGINGFACEHUB_API_TOKEN="$${HUGGINGFACEHUB_API_TOKEN:-}" && \
	source scripts/setup_env.sh 2>/dev/null || true && \
	cd tests && \
	poetry run pytest \
		--model-runtime=$(shell echo $(BACKEND_UPPER) | tr '[:upper:]' '[:lower:]') \
		--verbose \
		--cov=app \
		--cov-report=html:../coverage-backend \
		--cov-report=xml:../coverage-backend.xml \
		--cov-report=term-missing \
		--cov-branch && \
	cd .. && \
	deactivate && \
	rm -rf chat-qna-core-venv

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
	@if [ "$(BACKEND_UPPER)" = "OLLAMA" ]; then \
		echo "  BACKEND:      $(BACKEND_UPPER) (CPU only)"; \
		echo "  DEVICE:       CPU"; \
		BACKEND_TAG_COMPUTED="$${BACKEND_TAG:-$(DEFAULT_OLLAMA_TAG)}"; \
	else \
		echo "  BACKEND:      $(BACKEND_UPPER)"; \
		echo "  DEVICE:       $(DEVICE_UPPER)"; \
		if [ "$(DEVICE_UPPER)" = "GPU" ]; then \
			BACKEND_TAG_COMPUTED="$${BACKEND_TAG:-$(DEFAULT_GPU_TAG)}"; \
		else \
			BACKEND_TAG_COMPUTED="$${BACKEND_TAG:-$(DEFAULT_BACKEND_TAG)}"; \
		fi; \
	fi; \
	echo ""; \
	echo "Images:"; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "  REGISTRY:     $${REGISTRY:-$(DEFAULT_REGISTRY)}"; \
	echo "  UI_TAG:       $${UI_TAG:-$(DEFAULT_UI_TAG)}"; \
	echo "  BACKEND_TAG:  $$BACKEND_TAG_COMPUTED"; \
	if [ "$(BACKEND_UPPER)" = "OPENVINO" ]; then \
		if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
			echo "  HF_TOKEN:     ❌ NOT SET"; \
		else \
			echo "  HF_TOKEN:     ✅ Set"; \
		fi; \
	else \
		echo "  HF_TOKEN:     (not required for Ollama)"; \
	fi; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo ""; \
	VALIDATION_ERROR=""; \
	if [ "$(BACKEND_UPPER)" = "OPENVINO" ] && [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
		echo "❌ HUGGINGFACEHUB_API_TOKEN is required for OpenVINO backend."; \
		echo "   export HUGGINGFACEHUB_API_TOKEN=<your-token>"; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(BACKEND_UPPER)" != "OPENVINO" ] && [ "$(BACKEND_UPPER)" != "OLLAMA" ]; then \
		echo "❌ Invalid BACKEND '$(BACKEND_UPPER)'. Use OPENVINO or OLLAMA."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ "$(BACKEND_UPPER)" = "OPENVINO" ] && [ "$(DEVICE_UPPER)" != "CPU" ] && [ "$(DEVICE_UPPER)" != "GPU" ]; then \
		echo "❌ Invalid DEVICE '$(DEVICE_UPPER)'. Use CPU or GPU."; \
		echo ""; \
		VALIDATION_ERROR="true"; \
	fi; \
	if [ -n "$$VALIDATION_ERROR" ]; then \
		exit 0; \
	fi; \
	read -p "Proceed with deployment? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		echo ""; \
		echo "Deployment cancelled."; \
		echo ""; \
	else \
		echo ""; \
		echo "→ Deploying..."; \
		if [ "$(BACKEND_UPPER)" = "OLLAMA" ]; then \
			export BACKEND_TAG="$${BACKEND_TAG:-$(DEFAULT_OLLAMA_TAG)}"; \
			export UI_TAG="$${UI_TAG:-$(DEFAULT_UI_TAG)}"; \
			export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}"; \
			bash -c "source scripts/setup_env.sh -b ollama && docker compose -f docker/compose.yaml up -d"; \
		elif [ "$(DEVICE_UPPER)" = "GPU" ]; then \
			export BACKEND_TAG="$${BACKEND_TAG:-$(DEFAULT_GPU_TAG)}"; \
			export UI_TAG="$${UI_TAG:-$(DEFAULT_UI_TAG)}"; \
			export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}"; \
			bash -c "source scripts/setup_env.sh -d gpu && docker compose -f docker/compose.yaml up -d"; \
		else \
			export BACKEND_TAG="$${BACKEND_TAG:-$(DEFAULT_BACKEND_TAG)}"; \
			export UI_TAG="$${UI_TAG:-$(DEFAULT_UI_TAG)}"; \
			export REGISTRY="$${REGISTRY:-$(DEFAULT_REGISTRY)}"; \
			bash -c "source scripts/setup_env.sh && docker compose -f docker/compose.yaml up -d"; \
		fi; \
		echo ""; \
		echo "✅ Deployment complete!"; \
	fi

deploy-build:
	@bash -c '\
		echo "══════════════════════════════════════════════════"; \
		echo "🚀 Deploy Build - $(SERVICE_NAME)"; \
		echo "══════════════════════════════════════════════════"; \
		echo ""; \
		echo "Configuration:"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		if [ "$(BACKEND_UPPER)" = "OLLAMA" ]; then \
			echo "  BACKEND:   $(BACKEND_UPPER) (CPU only)"; \
			echo "  DEVICE:    CPU"; \
		else \
			echo "  BACKEND:   $(BACKEND_UPPER)"; \
			echo "  DEVICE:    $(DEVICE_UPPER)"; \
		fi; \
		if [ "$(BACKEND_UPPER)" = "OPENVINO" ]; then \
			if [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
				echo "  HF_TOKEN:  ❌ NOT SET"; \
			else \
				echo "  HF_TOKEN:  ✅ Set"; \
			fi; \
		else \
			echo "  HF_TOKEN:  (not required for Ollama)"; \
		fi; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo ""; \
		if [ "$(BACKEND_UPPER)" = "OPENVINO" ] && [ -z "$${HUGGINGFACEHUB_API_TOKEN:-}" ]; then \
			echo "❌ HUGGINGFACEHUB_API_TOKEN is required for OpenVINO backend."; \
			echo "   export HUGGINGFACEHUB_API_TOKEN=<your-token>"; \
			echo ""; \
			exit 0; \
		elif [ "$(BACKEND_UPPER)" != "OPENVINO" ] && [ "$(BACKEND_UPPER)" != "OLLAMA" ]; then \
			echo "❌ Invalid BACKEND '\''$(BACKEND_UPPER)'\''. Use OPENVINO or OLLAMA."; \
			exit 0; \
		elif [ "$(BACKEND_UPPER)" = "OPENVINO" ] && [ "$(DEVICE_UPPER)" != "CPU" ] && [ "$(DEVICE_UPPER)" != "GPU" ]; then \
			echo "❌ Invalid DEVICE '\''$(DEVICE_UPPER)'\''. Use CPU or GPU."; \
			exit 0; \
		else \
			read -p "Proceed with deployment? [y/N]: " confirm; \
			if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
				echo ""; \
				echo "Deployment cancelled."; \
				echo ""; \
			else \
				echo ""; \
				echo "→ Building and deploying..."; \
				if [ "$(BACKEND_UPPER)" = "OLLAMA" ]; then \
					source scripts/setup_env.sh -b ollama && docker compose -f docker/compose.yaml up -d --build; \
				elif [ "$(DEVICE_UPPER)" = "GPU" ]; then \
					source scripts/setup_env.sh -d gpu && docker compose -f docker/compose.yaml up -d --build; \
				else \
					source scripts/setup_env.sh && docker compose -f docker/compose.yaml up -d --build; \
				fi; \
				echo ""; \
				echo "✅ Deployment complete!"; \
			fi; \
		fi; \
	'

undeploy:
	@echo "══════════════════════════════════════════════════"
	@echo "🛑 Stopping $(SERVICE_NAME)"
	@echo "══════════════════════════════════════════════════"
	@if [ "$(BACKEND_UPPER)" = "OLLAMA" ]; then \
		bash -c "source scripts/setup_env.sh -b ollama 2>/dev/null || true && docker compose -f docker/compose.yaml down"; \
	elif [ "$(DEVICE_UPPER)" = "GPU" ]; then \
		bash -c "source scripts/setup_env.sh -d gpu 2>/dev/null || true && docker compose -f docker/compose.yaml down"; \
	else \
		bash -c "source scripts/setup_env.sh 2>/dev/null || true && docker compose -f docker/compose.yaml down"; \
	fi
	@echo "✅ Application stopped."

# ==============================================================================
# Code Quality
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
	@echo "Scanning backend image..."
	@trivy image --severity HIGH,CRITICAL --format table \
		--output security-results/trivy-image-$(SERVICE_NAME)-backend.txt \
		$(SERVICE_NAME)-backend:$(VERSION) 2>/dev/null || echo "⚠️  Backend image not found. Run 'make build' first."
	@trivy image --severity HIGH,CRITICAL --format spdx-json --scanners vuln \
		--output security-results/trivy-image-$(SERVICE_NAME)-backend-spdx.json \
		$(SERVICE_NAME)-backend:$(VERSION) 2>/dev/null || true
	@echo "Scanning frontend image..."
	@trivy image --severity HIGH,CRITICAL --format table \
		--output security-results/trivy-image-$(SERVICE_NAME)-frontend.txt \
		$(SERVICE_NAME)-frontend:$(VERSION) 2>/dev/null || echo "⚠️  Frontend image not found. Run 'make build' first."
	@trivy image --severity HIGH,CRITICAL --format spdx-json --scanners vuln \
		--output security-results/trivy-image-$(SERVICE_NAME)-frontend-spdx.json \
		$(SERVICE_NAME)-frontend:$(VERSION) 2>/dev/null || true
	@echo "✅ Image scans complete: security-results/trivy-image-*"

trivy-scan-config:
	@echo "🔍 Running Trivy Config Scans..."
	@mkdir -p security-results
	@trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME)-backend.json \
		--file-patterns "dockerfile:Dockerfile" . || true
	@trivy config --severity HIGH,CRITICAL --format json \
		--output security-results/trivy-config-$(SERVICE_NAME)-frontend.json \
		--file-patterns "dockerfile:Dockerfile" ui/ || true
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
	@echo "║          Chat Question & Answer Core - Makefile                  ║"
	@echo "╚══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "BUILD & TEST"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  build            Build all Docker images"
	@echo "  test             Run all unit tests"
	@echo "  test-frontend    Run frontend tests"
	@echo "  test-backend     Run backend tests (uses BACKEND env var)"
	@echo ""
	@echo "DEPLOYMENT"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  deploy           Deploy using pre-built images"
	@echo "  deploy-build     Build images and deploy"
	@echo "  undeploy         Stop and remove containers"
	@echo ""
	@echo "  Environment Variables:"
	@echo "    BACKEND                    OPENVINO (default) or OLLAMA"
	@echo "    DEVICE                     CPU (default) or GPU (OpenVINO only)"
	@echo "    HUGGINGFACEHUB_API_TOKEN   Required for OpenVINO"
	@echo "    REGISTRY                   Image registry (default: $(DEFAULT_REGISTRY))"
	@echo "    UI_TAG                     UI image tag (default: $(DEFAULT_UI_TAG))"
	@echo "    BACKEND_TAG                Backend image tag (auto-selected by BACKEND/DEVICE)"
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
	@echo "  # Deploy with pre-built images (OpenVINO CPU)"
	@echo "  export HUGGINGFACEHUB_API_TOKEN=<token>"
	@echo "  make deploy"
	@echo ""
	@echo "  # Deploy with Ollama"
	@echo "  BACKEND=OLLAMA make deploy"
	@echo ""
	@echo "  # Build and deploy with OpenVINO GPU"
	@echo "  export HUGGINGFACEHUB_API_TOKEN=<token>"
	@echo "  DEVICE=GPU make deploy-build"
	@echo ""
