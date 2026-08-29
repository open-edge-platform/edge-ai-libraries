# SPDX-FileCopyrightText: Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# ==============================================================================
# Agentic Predictive Maintenance Blueprint - Makefile
# ==============================================================================
#
# Quick Start:
#   make help              - Show all available commands
#   make build             - Build all application Docker images
#   make test              - Run all unit tests
#   make lint              - Run linters for all components
#   make trivy-scan        - Run Trivy security scans
#
# ==============================================================================

SHELL := bash -eu -o pipefail
.DEFAULT_GOAL := help

# ==============================================================================
# Project Configuration
# ==============================================================================

SERVICE_NAME := apm
VERSION ?= latest
PYTHON_VERSION := 3.12

DEFAULT_REGISTRY := intel/
DEFAULT_TAG := 1.0.0

REGISTRY ?= $(DEFAULT_REGISTRY)
TAG ?= $(DEFAULT_TAG)

# ==============================================================================
# Component Configuration
# ==============================================================================

COMPONENTS := agent-service storage-service ui-service
TEST_COMPONENTS := agent-service storage-service ui-service

agent-service_CONTEXT_DIR  := ./services/agent-service
agent-service_DOCKERFILE   := ./services/agent-service/Dockerfile
agent-service_LANG         := python

storage-service_CONTEXT_DIR := ./services/storage-service
storage-service_DOCKERFILE  := ./services/storage-service/Dockerfile
storage-service_LANG        := python

ui-service_CONTEXT_DIR := ./services/ui-service
ui-service_DOCKERFILE  := ./services/ui-service/Dockerfile
ui-service_LANG        := python

# ==============================================================================
# Build Targets
# ==============================================================================

.PHONY: build
build: $(addprefix build-, $(COMPONENTS))  ## Build all Docker images
	@echo "All images built successfully."

define BUILD_COMPONENT
.PHONY: build-$(1)
build-$(1):  ## Build $(1) Docker image
	@echo "Building $(1)..."
	docker build \
		--build-arg http_proxy=$(http_proxy) \
		--build-arg https_proxy=$(https_proxy) \
		--build-arg no_proxy=$(no_proxy) \
		-t $(REGISTRY)apm-$(1):$(TAG) \
		-f $($(1)_DOCKERFILE) \
		$($(1)_CONTEXT_DIR)
	@echo "$(1) built: $(REGISTRY)apm-$(1):$(TAG)"
endef

$(foreach component,$(COMPONENTS),$(eval $(call BUILD_COMPONENT,$(component))))

# ==============================================================================
# Test Targets
# ==============================================================================

.PHONY: test
test: $(addprefix test-, $(TEST_COMPONENTS))  ## Run all unit tests

define TEST_COMPONENT
.PHONY: test-$(1)
test-$(1):  ## Run unit tests for $(1)
	@echo "Testing $(1)..."
	cd $($(1)_CONTEXT_DIR) && \
		python$(PYTHON_VERSION) -m pytest tests/ -v --tb=short
endef

$(foreach component,$(TEST_COMPONENTS),$(eval $(call TEST_COMPONENT,$(component))))

# ==============================================================================
# Lint Targets
# ==============================================================================

.PHONY: lint
lint: $(addprefix lint-, $(COMPONENTS))  ## Run linters for all components

define LINT_COMPONENT
.PHONY: lint-$(1)
lint-$(1):  ## Lint $(1)
	@echo "Linting $(1)..."
	cd $($(1)_CONTEXT_DIR) && \
		python$(PYTHON_VERSION) -m pylint src/ --fail-under=7.0 || true && \
		python$(PYTHON_VERSION) -m bandit -r src/ -ll || true
endef

$(foreach component,$(COMPONENTS),$(eval $(call LINT_COMPONENT,$(component))))

# ==============================================================================
# Security Scan
# ==============================================================================

.PHONY: trivy-scan
trivy-scan: $(addprefix trivy-scan-, $(COMPONENTS))  ## Run Trivy security scans on all images

define TRIVY_SCAN_COMPONENT
.PHONY: trivy-scan-$(1)
trivy-scan-$(1):  ## Trivy scan $(1)
	@echo "Trivy scan: $(1)..."
	trivy image $(REGISTRY)apm-$(1):$(TAG)
endef

$(foreach component,$(COMPONENTS),$(eval $(call TRIVY_SCAN_COMPONENT,$(component))))

# ==============================================================================
# Help
# ==============================================================================

.PHONY: help
help:  ## Show available make targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
