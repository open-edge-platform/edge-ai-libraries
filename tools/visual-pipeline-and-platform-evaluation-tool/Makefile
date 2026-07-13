# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SHELL := bash -eu -o pipefail

# default goal to show help
.DEFAULT_GOAL := help
.PHONY: all lint build mdlint ruff fix-linter format pyright run build-dev run-dev test \
	shell shell-vippet shell-model-download shell-metrics-manager shell-videogenerator stop clean clean-output-videos help \
	build-videogenerator build-onvif-discovery docker-build env-setup build-test \
	test-smoke test-full

# Project Variables
PROJECT_NAME := vippet
PROJECT_DIR := $(shell pwd)

# Docker Compose Variables
COMPOSE_FILE := compose.yml
DEV_COMPOSE_FILE := compose.dev.yml

# Speed up `docker compose build` by skipping provenance/SBOM attestations
# (saves ~hundreds of ms per build on warm cache, more on cold).
export BUILDX_NO_DEFAULT_ATTESTATIONS := 1

# Python venv Target
VENV_DIR := .venv
VENV_SENTINEL := $(VENV_DIR)/.installed

# env-setup sentinel for the (slow-changing) directory layout. setup_env.sh
# is intentionally NOT gated by this sentinel — it must run on every
# invocation because its output (.env / COMPOSE_PROFILES) depends on the
# currently installed hardware drivers, which can change without any
# repo file changing.
ENV_DIRS_SENTINEL := shared/.env-dirs.done

# Test image build sentinel: re-build only when inputs that actually
# affect the test image change (Dockerfile or requirements files). All
# other source files are bind-mounted at run-time via --volume. Lives
# under shared/ so it sits next to other generated artifacts and is
# covered by the existing shared/* ignore patterns.
TEST_IMAGE_SENTINEL := shared/.vippet-test-image.stamp

# Create the dev venv only when requirements change. A sentinel file is
# used instead of the venv directory itself because the directory mtime
# is unstable across pip installs, which can cause the recipe
# to run on every invocation.
$(VENV_SENTINEL): $(PROJECT_NAME)/requirements.txt $(PROJECT_NAME)/requirements-dev.txt
	@if [ ! -d $(VENV_DIR) ]; then python3 -m venv $(VENV_DIR); fi
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	python -m pip install -r $(PROJECT_NAME)/requirements-dev.txt
	@touch $@

all: lint build run test ## Run lint, build, run and test

lint: $(VENV_SENTINEL) mdlint ruff pyright ## Run all linters

# Limit the markdown file search to source-controlled docs only. Excluding
# generated/vendored trees (.venv, ui/node_modules, ui/dist, .pytest_cache)
# avoids both spurious lint errors and slow filesystem scans.
MD_FILES := $(shell find . -type f -name '*.md' \
	-not -path './.*' \
	-not -path './shared/*' \
	-not -path './.venv/*' \
	-not -path './ui/node_modules/*' \
	-not -path './ui/dist/*' \
	-not -path '*/.pytest_cache/*' \
	-not -path '*/__pycache__/*' \
	-print)
mdlint: ## Lint MD files
# download tool from https://github.com/igorshubovych/markdownlint-cli
	markdownlint --version
	markdownlint $(MD_FILES)

ruff: $(VENV_SENTINEL) ## Run ruff linter
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	ruff --version ;\
	# Exclude shared/ — runtime-mounted volume, not source code ;\
	ruff check --exclude shared/ ;\
	ruff format --check --exclude shared/

fix-linter: $(VENV_SENTINEL) ## Fix linter issues using ruff
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	# Exclude shared/ — runtime-mounted volume, not source code ;\
	ruff check --fix --exclude shared/

format: $(VENV_SENTINEL) ## Format code using ruff
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	# Exclude shared/ — runtime-mounted volume, not source code ;\
	ruff format --exclude shared/

pyright: $(VENV_SENTINEL) ## Run pyright type checker
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	pyright --version ;\
	# Include/exclude is configured in pyrightconfig.json. ;\
	pyright --threads=4

generate_openapi: $(VENV_SENTINEL) ## Generate OpenAPI schema file
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	cd $(PROJECT_NAME) ;\
	PYTHONPATH=. SUPPORTED_MODELS_FILE=../shared/models/supported_models.yaml AUTO_VIDEO_DIR=../shared/videos/input/auto UPLOADED_VIDEO_DIR=../shared/videos/input/uploaded python ../generate_openapi.py

# Directory layout for the shared/ runtime volumes. Cheap and idempotent
# but sentinel-gated so repeated invocations skip the chmod chatter.
$(ENV_DIRS_SENTINEL): Makefile
	mkdir -p shared/metadata && chmod o+w shared/metadata
	mkdir -p shared/models/output && chmod o+w shared/models/output
	mkdir -p shared/model-download/cache && chmod o+w shared/model-download/cache
	for v in base huggingface ultralytics pipeline-zoo-models openvino geti hls; do \
		mkdir -p shared/model-download/venv-$$v && chmod o+w shared/model-download/venv-$$v ; \
	done
	mkdir -p shared/images/input && chmod o+w shared/images/input
	mkdir -p shared/images/output && chmod o+w shared/images/output
	mkdir -p shared/videos/input && chmod o+w shared/videos/input
	mkdir -p shared/videos/output && chmod o+w shared/videos/output
	mkdir -p shared/videos/video-generator && chmod o+w shared/videos/video-generator
	@touch $@

# env-setup must run on every invocation: setup_env.sh detects the
# currently installed hardware drivers (NPU/GPU/CPU) and rewrites .env
# with the matching COMPOSE_PROFILES. That can change without any
# tracked file changing, so we never cache the script's output.
env-setup: $(ENV_DIRS_SENTINEL) ## Create shared/ dirs and (always) re-run setup_env.sh
	./setup_env.sh

build: env-setup ## Build core images (vippet-app, vippet-ui, vippet-onvif-discovery)
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml build

build-dev: env-setup ## Build core dev images (vippet-app, vippet-ui, vippet-onvif-discovery)
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml -f $(DEV_COMPOSE_FILE) build

build-videogenerator: env-setup ## Build videogenerator image
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml build videogenerator

build-onvif-discovery: env-setup ## Build onvif discovery image
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml build onvif-discovery

docker-build: build build-videogenerator ## Build all images

run: env-setup ## Run the docker compose services
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml up -d

run-videogenerator: env-setup build-videogenerator ## Run only the videogenerator service
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml up -d videogenerator

run-dev: env-setup ## Run the docker compose services for development
	. .env && docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml -f $(DEV_COMPOSE_FILE) up -d

# Build the test image only when its inputs change. Source files are
# bind-mounted at run-time (see `test` target), so changing application
# code does not require an image rebuild.
#
# `env-setup` is an order-only prerequisite (after the `|`): it must
# run first so .env exists, but its always-changing timestamp must not
# invalidate this sentinel.
$(TEST_IMAGE_SENTINEL): $(PROJECT_NAME)/Dockerfile \
		$(PROJECT_NAME)/requirements.txt \
		$(PROJECT_NAME)/requirements-dev.txt \
		$(PROJECT_NAME)/requirements-omz.txt \
		.dockerignore \
		| env-setup
	. .env && TARGET=test DOCKER_TAG="test" docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml build vippet
	@touch $@

build-test: $(TEST_IMAGE_SENTINEL) ## Build the vippet test image (with dev deps)

test: build-test ## Run unit tests and generate coverage report
    # Run tests using the cpu profile (tests are device agnostic)
    # Override DOCKER_TAG with '-test' suffix only for this docker compose run
    # NOTE: `--build` is intentionally omitted — image is built by the
    # `build-test` prerequisite, and only when its inputs change.
	. .env && TARGET=test DOCKER_TAG="test" docker compose -f $(COMPOSE_FILE) -f compose.$$COMPOSE_PROFILES.yml run \
	--rm --no-deps --volume $(PROJECT_DIR):/home/dlstreamer/vippet vippet bash -c "\
		cd $(PROJECT_NAME) && \
		AUTO_VIDEO_DIR=/tmp/auto \
		UPLOADED_VIDEO_DIR=/tmp/uploaded \
		OUTPUT_VIDEO_DIR=/tmp \
		METADATA_DIR=/tmp \
		python -m coverage run --branch --source=./ --data-file=/tmp/.vippet-coverage -m unittest discover -v -s ./tests/unit -p '*_test.py' && \
		python -m coverage report --data-file=/tmp/.vippet-coverage --show-missing --skip-covered --omit=*/config-3.py,*/config.py,*_test.py && \
		python -m coverage html --data-file=/tmp/.vippet-coverage --directory=/tmp/.vippet-coverage-html --omit=*/config-3.py,*/config.py,*_test.py"

test-smoke: $(VENV_SENTINEL) ## Run smoke functional tests
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	python -m pytest --log-cli-level=INFO -m smoke vippet/tests/functional/

test-full: $(VENV_SENTINEL) ## Run full functional tests
	set +u; . ./$(VENV_DIR)/bin/activate; set -u ;\
	python -m pytest --log-cli-level=INFO vippet/tests/functional/

shell: env-setup ## Open shell in specified container (i.e. make shell SERVICE=vippet)
	docker exec -it $(SERVICE) bash

shell-vippet: ## Open shell in vippet container
	$(MAKE) shell SERVICE=vippet

shell-model-download: ## Open shell in model-download container
	$(MAKE) shell SERVICE=model-download

shell-metrics-manager: ## Open shell in metrics-manager container
	$(MAKE) shell SERVICE=metrics-manager

shell-videogenerator: ## Open shell in videogenerator container
	$(MAKE) shell SERVICE=videogenerator

stop: ## Stop the docker compose services
	docker compose down model-download metrics-manager videogenerator mediamtx vippet-ui vippet onvif-discovery

clean: clean-model-download clean-models clean-output-videos ## Clean all build artifacts
	rm -rf shared/onvif/onvif_cameras.json shared/videos/input shared/videos/video-generator
	rm -f $(ENV_DIRS_SENTINEL) $(TEST_IMAGE_SENTINEL)

clean-model-download: ## Clean only model-download artifacts
	docker run --rm -v "${PWD}"/shared/model-download/:/mnt/model-download/ python:3.12-slim sh -c 'rm -rf /mnt/model-download/cache/ /mnt/model-download/venv-*/'

clean-models: ## Clean only models
	docker run --rm -v "${PWD}"/shared/models/:/mnt/models/ python:3.12-slim sh -c 'rm -rf /mnt/models/output/'

clean-output-videos: ## Clean only output videos
	rm -rf shared/videos/output/*

help: ## Print help for each target
	@echo ViPPET make targets
	@echo "Target               Makefile:Line    Description"
	@echo "-------------------- ---------------- -----------------------------------------"
	@grep -H -n '^[[:alnum:]_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort -t ":" -k 3 \
    | awk 'BEGIN  {FS=":"}; {sub(".* ## ", "", $$4)}; {printf "%-20s %-16s %s\n", $$3, $$1 ":" $$2, $$4};'
