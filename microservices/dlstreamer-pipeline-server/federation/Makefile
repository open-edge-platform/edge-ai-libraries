# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

IMAGE_NAME ?= dlsps-federation-proxy
IMAGE_TAG  ?= latest

.PHONY: all build lint test coverage help

all: build lint test

build: ## Build Docker image
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

lint: ## Run linters
	pylint src/

test: ## Run unit tests
	python -m pytest tests/ -v

coverage: ## Run tests with coverage
	python -m pytest tests/ -v --cov=src --cov-report=term-missing

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'
