# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL := bash -eu -o pipefail

# default goal to show help
.DEFAULT_GOAL := help
.PHONY: all lint build mdlint ruff fix-linter format pyright run build-dev run-dev test \
	shell shell-vippet shell-models shell-collector shell-videogenerator stop clean help \
	build-videogenerator build-models docker-build env-setup \
	install-models-once install-models-force install-models-all

# Project Variables
PROJECT_NAME := vippet
PROJECT_DIR := $(shell pwd)

# Docker Compose Variables
COMPOSE_FILE := compose.yml
DEV_COMPOSE_FILE := compose.dev.yml

# Python venv Target
VENV_DIR := .venv

$(VENV_DIR): $(PROJECT_NAME)/requirements.txt ## Create Python venv
	python3 -m venv $@ ;\
	set +u; . ./$@/bin/activate; set -u ;\
	python -m pip install --upgrade pip ;\
	python -m pip install -r $(PROJECT_NAME)/requirements-dev.txt

all: lint build run test ## Run lint, build, run and test

lint: $(VENV_DIR) mdlint ruff pyright ## Run all linters

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

# Environment setup target: always run before build/run targets that need .env
env-setup:
	./setup_env.sh

build: env-setup ## Build core images (vippet-app, vippet-collector)
	docker compose build

build-dev: env-setup ## Build core dev images (vippet-app, vippet-collector)
	docker compose -f $(COMPOSE_FILE) -f $(DEV_COMPOSE_FILE) build

build-videogenerator: env-setup ## Build videogenerator image
	docker compose build videogenerator

build-models: env-setup ## Build model image
	docker compose build models

docker-build: build build-videogenerator build-models ## Build all images

run: env-setup install-models-once ## Run the docker compose services
	docker compose up -d

run-videogenerator: env-setup build-videogenerator ## Run only the videogenerator service
	mkdir -p shared/videos && chmod o+w shared/videos
	docker compose up -d videogenerator

run-dev: env-setup install-models-once ## Run the docker compose services for development
	docker compose -f $(COMPOSE_FILE) -f $(DEV_COMPOSE_FILE) up -d

test: env-setup ## Run tests and generate coverage report
    # Run tests using the vippet-cpu container (tests are device agnostic)
    # Override DOCKER_TAG with '-test' suffix only for this docker compose run
	TARGET=test DOCKER_TAG="test" docker compose -f $(COMPOSE_FILE) run \
	--build --rm --no-deps --volume $(PROJECT_DIR):/home/dlstreamer/vippet vippet-cpu bash -c "\
		cd $(PROJECT_NAME) && \
		python -m coverage run --source=./ --data-file=/tmp/.vippet-coverage -m unittest discover -v -s ./tests -p '*_test.py' && \
		python -m coverage report --data-file=/tmp/.vippet-coverage --omit=*/config-3.py,*/config.py,*_test.py"

install-models-once: env-setup ## Handle models download and installation (once)
	mkdir -p shared/models/output && chmod o+w shared/models/output
	MODEL_INSTALLATION=once docker compose run --rm -it models

install-models-force: env-setup ## Handle models download and installation (force)
	mkdir -p shared/models/output && chmod o+w shared/models/output
	MODEL_INSTALLATION=force docker compose run --rm -it models

install-models-all: env-setup ## Install all models automatically (no dialog)
	mkdir -p shared/models/output && chmod o+w shared/models/output
	MODEL_INSTALLATION=all docker compose run --rm -it models

shell: env-setup ## Open shell in specified container (i.e. make shell SERVICE=vippet)
	docker exec -it $(SERVICE) bash

shell-vippet: env-setup ## Open shell in vippet container
	$(MAKE) shell SERVICE=vippet

shell-models: env-setup ## Open shell in models container
	$(MAKE) shell SERVICE=models

shell-collector: env-setup ## Open shell in collector container
	$(MAKE) shell SERVICE=collector

shell-videogenerator: env-setup ## Open shell in videogenerator container
	$(MAKE) shell SERVICE=videogenerator

stop: ## Stop the docker compose services
	@VIPPET_SERVICE=$$(docker compose ps --services | grep "^vippet-" | head -n 1 || echo ""); \
	docker compose down models collector videogenerator $$VIPPET_SERVICE

clean: ## Clean all build artifacts
	rm -rf shared/models/output/ shared/videos/

help: ## Print help for each target
	@echo ViPPET make targets
	@echo "Target               Makefile:Line    Description"
	@echo "-------------------- ---------------- -----------------------------------------"
	@grep -H -n '^[[:alnum:]_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort -t ":" -k 3 \
    | awk 'BEGIN  {FS=":"}; {sub(".* ## ", "", $$4)}; {printf "%-20s %-16s %s\n", $$3, $$1 ":" $$2, $$4};'
