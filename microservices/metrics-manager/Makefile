# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Metrics Manager - convenience targets for build/test/run.
#
# The image tag is read from the VERSION file (single source of truth).
# Override on the command line:  `make build TAG=dev`

VERSION := $(shell cat VERSION 2>/dev/null | tr -d '[:space:]')
TAG     ?= $(VERSION)
REGISTRY ?=
INSTALL_OPENVINO ?= false

# Third-party component versions (Telegraf, qmassa, toolchain images).
# versions.env is the single source of truth; the Dockerfile only carries
# mirrored ARG defaults so a plain `docker build .` still works. Edit
# versions.env, then run `make sync-versions`.
include versions.env
export TELEGRAF_VERSION TELEGRAF_SHA256 QMASSA_VERSION QMMD_VERSION
export RUST_IMAGE GO_IMAGE PYTHON_IMAGE

# Passed to every image build so the pins in versions.env win over the
# Dockerfile ARG defaults.
BUILD_ARGS := \
	--build-arg TELEGRAF_VERSION=$(TELEGRAF_VERSION) \
	--build-arg TELEGRAF_SHA256=$(TELEGRAF_SHA256) \
	--build-arg QMASSA_VERSION=$(QMASSA_VERSION) \
	--build-arg QMMD_VERSION=$(QMMD_VERSION) \
	--build-arg RUST_IMAGE=$(RUST_IMAGE) \
	--build-arg GO_IMAGE=$(GO_IMAGE) \
	--build-arg PYTHON_IMAGE=$(PYTHON_IMAGE)

# Helm packaging configuration. Charts are pushed to the same OCI path as
# the container image; the chart version carries a `-helm` suffix so the
# two artefacts coexist under intel/metrics-manager:<X.Y.Z> (image) and
# intel/metrics-manager:<X.Y.Z>-helm (chart). The chart is versioned independently.
HELM_CHART_DIR     := helm/metrics-manager
HELM_CHART_VERSION := $(shell sed -n 's/^version:[[:space:]]*//p' $(HELM_CHART_DIR)/Chart.yaml)
HELM_OCI_REGISTRY  ?= oci://registry-1.docker.io/intel
HELM_PACKAGE_DIR   := dist/helm

export TAG
export REGISTRY
export INSTALL_OPENVINO

.PHONY: help version versions sync-versions build build-test up down logs test clean bump \
        helm-lint helm-template helm-package helm-push generate-helm

help:
	@echo "Metrics Manager - available targets:"
	@echo "  make version            Print the version read from VERSION"
	@echo "  make versions           Print the third-party pins read from versions.env"
	@echo "  make sync-versions      Mirror versions.env into the Dockerfile ARG defaults"
	@echo "  make build              Build the slim metrics-manager image tagged $(REGISTRY)metrics-manager:$(TAG)"
	@echo "  INSTALL_OPENVINO=true make build  Build extended with OpenVINO GPU/NPU runtimes and Intel media VA drivers"
	@echo "  make build-test         Build the metrics-manager-test image"
	@echo "  make up                 Start the stack (docker compose up -d)"
	@echo "  make down               Stop the stack"
	@echo "  make logs               Tail container logs"
	@echo "  make test               Run pytest inside the test image"
	@echo "  make clean              Remove built images and stopped containers"
	@echo "  make bump NEW=2026.3.0  Update legacy application mirrors (not Helm); see README"
	@echo ""
	@echo "Helm chart targets (require the 'helm' CLI):"
	@echo "  make helm-lint          helm lint $(HELM_CHART_DIR)"
	@echo "  make helm-template      Render the chart with default values"
	@echo "  make helm-package       Package the chart into $(HELM_PACKAGE_DIR)/metrics-manager-$(HELM_CHART_VERSION).tgz"
	@echo "  make generate-helm      Alias for helm-lint + helm-package"
	@echo "  make helm-push          Push the packaged chart to $(HELM_OCI_REGISTRY)"
	@echo ""
	@echo "Override the tag for a one-off build:  make build TAG=dev"

version:
	@echo $(VERSION)

versions:
	@echo "TELEGRAF_VERSION = $(TELEGRAF_VERSION)"
	@echo "TELEGRAF_SHA256  = $(TELEGRAF_SHA256)"
	@echo "QMASSA_VERSION   = $(QMASSA_VERSION)"
	@echo "QMMD_VERSION     = $(QMMD_VERSION)"
	@echo "RUST_IMAGE       = $(RUST_IMAGE)"
	@echo "GO_IMAGE         = $(GO_IMAGE)"
	@echo "PYTHON_IMAGE     = $(PYTHON_IMAGE)"
	@echo "INTEL_COMPUTE_RUNTIME_VERSION = $(INTEL_COMPUTE_RUNTIME_VERSION)"
	@echo "INTEL_IGC_VERSION = $(INTEL_IGC_VERSION)"
	@echo "INTEL_GMMLIB_VERSION = $(INTEL_GMMLIB_VERSION)"
	@echo "INTEL_NPU_DRIVER_VERSION = $(INTEL_NPU_DRIVER_VERSION)"

# Mirror versions.env into the Dockerfile ARG defaults. Run this after editing
# versions.env; tests/test_versions.py fails if the two drift apart.
sync-versions:
	@sed -i.bak -E \
		-e 's|^ARG RUST_IMAGE=.*|ARG RUST_IMAGE=$(RUST_IMAGE)|' \
		-e 's|^ARG GO_IMAGE=.*|ARG GO_IMAGE=$(GO_IMAGE)|' \
		-e 's|^ARG PYTHON_IMAGE=.*|ARG PYTHON_IMAGE=$(PYTHON_IMAGE)|' \
		-e 's|^ARG QMASSA_VERSION=.*|ARG QMASSA_VERSION=$(QMASSA_VERSION)|' \
		-e 's|^ARG QMMD_VERSION=.*|ARG QMMD_VERSION=$(QMMD_VERSION)|' \
		-e 's|^ARG TELEGRAF_VERSION=.*|ARG TELEGRAF_VERSION=$(TELEGRAF_VERSION)|' \
		-e 's|^ARG TELEGRAF_SHA256=.*|ARG TELEGRAF_SHA256=$(TELEGRAF_SHA256)|' \
		Dockerfile && rm Dockerfile.bak
	@echo "Dockerfile ARG defaults synced from versions.env"

build:
	@test -n "$(VERSION)" || (echo "ERROR: VERSION file is missing or empty" && exit 1)
	docker compose build $(BUILD_ARGS) metrics-manager

build-test:
	docker compose build $(BUILD_ARGS) metrics-manager-test

up:
	docker compose up -d metrics-manager

down:
	docker compose down

logs:
	docker compose logs -f metrics-manager

test: build-test
	docker compose run --rm metrics-manager-test

clean:
	docker compose down --rmi local --volumes --remove-orphans
	rm -rf $(HELM_PACKAGE_DIR)

# -----------------------------------------------------------------------------
# Helm chart targets
# -----------------------------------------------------------------------------

helm-lint:
	@test -n "$(HELM_CHART_VERSION)" || (echo "ERROR: chart version is missing from $(HELM_CHART_DIR)/Chart.yaml" && exit 1)
	helm lint $(HELM_CHART_DIR)

helm-template:
	helm template metrics-manager $(HELM_CHART_DIR)

helm-package: helm-lint
	@mkdir -p $(HELM_PACKAGE_DIR)
	helm package $(HELM_CHART_DIR) --destination $(HELM_PACKAGE_DIR)
	@echo "Packaged: $(HELM_PACKAGE_DIR)/metrics-manager-$(HELM_CHART_VERSION).tgz"

# Alias used in docs - lints and packages the chart in one step.
generate-helm: helm-package

helm-push: helm-package
	helm push $(HELM_PACKAGE_DIR)/metrics-manager-$(HELM_CHART_VERSION).tgz $(HELM_OCI_REGISTRY)

# Update legacy application mirrors. Usage: make bump NEW=2026.3.0
# Review the complete release checklist in README; Helm is versioned separately.
# Updates: VERSION, pyproject.toml, .env, .env.example, compose.yaml,
#          app/settings.py, app/logging_config.py, docs/DOCKERHUB.md
bump:
	@test -n "$(NEW)" || (echo "ERROR: provide a new version with NEW=...  e.g. make bump NEW=2026.2.0" && exit 1)
	@echo "$(VERSION) -> $(NEW)"
	@echo "$(NEW)" > VERSION
	@sed -i.bak -E 's/^version = "[^"]+"/version = "$(NEW)"/' pyproject.toml && rm pyproject.toml.bak
	@sed -i.bak -E 's/^TAG=.+/TAG=$(NEW)/' .env && rm .env.bak
	@sed -i.bak -E 's/^TAG=.+/TAG=$(NEW)/' .env.example && rm .env.example.bak
	@sed -i.bak -E 's/(\$$\{TAG:-)[0-9][^}]*(\})/\1$(NEW)\2/g; s/(VERSION: \$$\{TAG:-)[0-9][^}]*(\})/\1$(NEW)\2/g' compose.yaml && rm compose.yaml.bak
	@sed -i.bak -E 's/(service_version: str = Field\(default=)"[^"]+"/\1"$(NEW)"/' app/settings.py && rm app/settings.py.bak
	@sed -i.bak -E 's/(service_version: str = )"[^"]+"/\1"$(NEW)"/' app/logging_config.py && rm app/logging_config.py.bak
	@sed -i.bak -E 's/(metrics-manager:)[0-9][0-9A-Za-z.+]*/\1$(NEW)/g; s/(Intel® Metrics Manager \*\*)[0-9][0-9A-Za-z.+-]*(\*\*)/\1$(NEW)\2/g' docs/DOCKERHUB.md && rm docs/DOCKERHUB.md.bak
	@echo "Done. Review the diff:  git diff"
	@echo "Then commit and (optionally) tag:  git add -A && git commit -m 'release: $(NEW)' && git tag v$(NEW)"
