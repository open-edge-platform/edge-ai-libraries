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

# Helm packaging configuration. Charts are pushed to the same OCI path as
# the container image; the chart version carries a `-helm` suffix so the
# two artefacts coexist under intel/metrics-manager:<X.Y.Z> (image) and
# intel/metrics-manager:<X.Y.Z>-helm (chart).
HELM_CHART_DIR     := helm/metrics-manager
HELM_CHART_VERSION := $(VERSION)-helm
HELM_OCI_REGISTRY  ?= oci://registry-1.docker.io/intel
HELM_PACKAGE_DIR   := dist/helm

export TAG
export REGISTRY

.PHONY: help version build build-test up down logs test clean bump \
        helm-lint helm-template helm-package helm-push generate-helm

help:
	@echo "Metrics Manager - available targets:"
	@echo "  make version            Print the version read from VERSION"
	@echo "  make build              Build the metrics-manager image tagged $(REGISTRY)metrics-manager:$(TAG)"
	@echo "  make build-test         Build the metrics-manager-test image"
	@echo "  make up                 Start the stack (docker compose up -d)"
	@echo "  make down               Stop the stack"
	@echo "  make logs               Tail container logs"
	@echo "  make test               Run pytest inside the test image"
	@echo "  make clean              Remove built images and stopped containers"
	@echo "  make bump NEW=2026.2.0  Update VERSION and all places that mirror it"
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

build:
	@test -n "$(VERSION)" || (echo "ERROR: VERSION file is missing or empty" && exit 1)
	docker compose build metrics-manager

build-test:
	docker compose build metrics-manager-test

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

# Bump the version everywhere it is mirrored. Usage:  make bump NEW=2026.2.0
# Updates: VERSION, pyproject.toml, .env, .env.example, compose.yaml,
#          app/settings.py, app/logging_config.py, docs/DOCKERHUB.md,
#          helm/metrics-manager/Chart.yaml (version + appVersion)
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
	@sed -i.bak -E 's/(metrics-manager:)[0-9][0-9A-Za-z.+]*/\1$(NEW)/g; s/--version [0-9][0-9A-Za-z.+]*-helm/--version $(NEW)-helm/g' docs/HELM.md && rm docs/HELM.md.bak
	@sed -i.bak -E 's/^version: [0-9][0-9A-Za-z.+-]*-helm/version: $(NEW)-helm/; s/^appVersion: "[^"]+"/appVersion: "$(NEW)"/' $(HELM_CHART_DIR)/Chart.yaml && rm $(HELM_CHART_DIR)/Chart.yaml.bak
	@echo "Done. Review the diff:  git diff"
	@echo "Then commit and (optionally) tag:  git add -A && git commit -m 'release: $(NEW)' && git tag v$(NEW)"
