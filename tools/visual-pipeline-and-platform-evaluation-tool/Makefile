# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL := bash -eu -o pipefail

# default goal to show help
.DEFAULT_GOAL := help
.PHONY: all lint build mdlint ruff fix-linter format pyright run build-dev run-dev test \
	shell shell-vippet shell-models shell-collector shell-videogenerator stop clean help

# Project Variables
PROJECT_NAME := vippet
PROJECT_DIR := $(shell pwd)

# Docker Compose Variables
COMPOSE_FILE := compose.yml
DEV_COMPOSE_FILE := compose.dev.yml

# Python venv Target
VENV_DIR := .venv

# Placeholder to prevent warnings about missing variables.
# This value is overridden by setup_env.sh in relevant targets.
export RENDER_GROUP_ID := 1000

$(VENV_DIR): requirements.txt ## Create Python venv
	python3 -m venv $@ ;\
	set +u; . ./$@/bin/activate; set -u ;\
	python -m pip install --upgrade pip ;\
	python -m pip install -r requirements-dev.txt

all: lint build run test ## Run lint, build, run and test

lint: $(VENV_DIR) mdlint pyright ruff ## Run all linters

MD_FILES := $(shell find . -type f \( -name '*.md' \) -not -path './.*' -print )
mdlint: ## Lint MD files
# download tool from https://github.com/igorshubovych/markdownlint-cli
	markdownlint --version
	markdownlint $(MD_FILES)

ruff: $(VENV_DIR) ## Run ruff linter
	set +u; . ./$</bin/activate; set -u ;\
	ruff --version ;\
	ruff check ;\
	ruff format --check

fix-linter: $(VENV_DIR) ## Fix linter issues using ruff
	set +u; . ./$</bin/activate; set -u ;\
	ruff check --fix

format: $(VENV_DIR) ## Format code using ruff
	set +u; . ./$</bin/activate; set -u ;\
	ruff format

pyright: $(VENV_DIR) ## Run pyright type checker
	set +u; . ./$</bin/activate; set -u ;\
	pyright --version ;\
	pyright .

check-device-type:
	@if [ -z "$(DEVICE_TYPE)" ]; then \
		echo "Error: DEVICE_TYPE is not set. Use 'make <target> DEVICE_TYPE=<GPU/CPU/NPU>'"; \
		exit 1; \
	fi; \

build: check-device-type $(VENV_DIR) ## Build all images
	source setup_env.sh -d $(DEVICE_TYPE) && \
	docker compose build

build-dev: check-device-type $(VENV_DIR) ## Build all dev images
	source setup_env.sh -d $(DEVICE_TYPE) && \
	docker compose -f $(COMPOSE_FILE) -f $(DEV_COMPOSE_FILE) build

run: check-device-type ## Run the docker compose services
	source setup_env.sh -d $(DEVICE_TYPE) && \
	docker compose up -d

run-dev: check-device-type ## Run the docker compose services for development
	source setup_env.sh -d $(DEVICE_TYPE) && \
	docker compose -f $(COMPOSE_FILE) -f $(DEV_COMPOSE_FILE) up -d

test: check-device-type ## Run tests
	source setup_env.sh -d $(DEVICE_TYPE) && \
	docker compose run --rm --no-deps --volume $(PROJECT_DIR):/home/dlstreamer/vippet \
		vippet-$(shell echo $(DEVICE_TYPE) | tr '[:upper:]' '[:lower:]') python -m unittest discover -v -s ./tests -p '*_test.py'

shell: ## Open shell in specified container (i.e. make shell SERVICE=vippet-gpu)
	docker exec -it $(SERVICE) bash

shell-vippet: ## Open shell in vippet-* container
	@VIPPET_SERVICE=$$(docker compose ps --services | grep "^vippet-" | head -n 1); \
	$(MAKE) shell SERVICE=$$VIPPET_SERVICE;

shell-models: ## Open shell in models container
	$(MAKE) shell SERVICE=models

shell-collector: ## Open shell in collector container
	$(MAKE) shell SERVICE=collector

shell-videogenerator: ## Open shell in videogenerator container
	$(MAKE) shell SERVICE=videogenerator

stop: ## Stop the docker compose services
	@VIPPET_SERVICE=$$(docker compose ps --services | grep "^vippet-" | head -n 1 || echo ""); \
	docker compose down models collector videogenerator $$VIPPET_SERVICE

clean: ## Clean all build artifacts
	rm -rf .collector-signals/ models/ videos/

help: ## Print help for each target
	@echo ViPPET make targets
	@echo "Target               Makefile:Line    Description"
	@echo "-------------------- ---------------- -----------------------------------------"
	@grep -H -n '^[[:alnum:]_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort -t ":" -k 3 \
    | awk 'BEGIN  {FS=":"}; {sub(".* ## ", "", $$4)}; {printf "%-20s %-16s %s\n", $$3, $$1 ":" $$2, $$4};'
