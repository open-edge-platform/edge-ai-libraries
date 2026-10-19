# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

BINARY_NAME    := stream-manager
BIN_DIR        := ./bin
BINARY_PATH    := $(BIN_DIR)/$(BINARY_NAME)
VERSION        := $(shell git describe --tags 2>/dev/null || echo dev)
BUILD_NUMBER   := $(shell git rev-list --count HEAD -- . 2>/dev/null || echo 0)
BUILD_DATE     := $(shell date +%Y-%m-%dT%H:%M:%S%z)
LDFLAGS        := -s -w \
	-X main.Version=$(VERSION) \
	-X main.BuildNumber=$(BUILD_NUMBER) \
	-X main.BuildDate=$(BUILD_DATE) \
	-extldflags '-z relro -z now'

IMAGE          ?= intel/stream-manager:latest
IMAGE_REF      := $(if $(findstring :,$(notdir $(IMAGE))),$(IMAGE),$(IMAGE):latest-dev)
CONTAINER_NAME := stream-manager
CONTAINER_PORT := 8080
ACCESS_PORT    ?= 8080

CONFIG_FILE    :=

DATA_VOLUME    := stream-manager-data
DATA_DIR       :=

DOCS_PATH      := /docs/v1/index.html

define PRINT_ACCESS_URLS
	echo "App (localhost): http://localhost:$$PORT/v1/status"; \
	echo "Docs (localhost): http://localhost:$$PORT$(DOCS_PATH)"; \
	REMOTE_IP="$$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p')"; \
	if [ -n "$$REMOTE_IP" ]; then \
		echo "App (remote): http://$$REMOTE_IP:$$PORT/v1/status"; \
		echo "Docs (remote): http://$$REMOTE_IP:$$PORT$(DOCS_PATH)"; \
	else \
		echo "No primary IPv4 address found. Check the host network configuration."; \
	fi
endef

.PHONY: help build run start access-urls docker-build docker-run docker-stop clean

help: ## Show this help
	@echo "Host targets:"
	@echo "  make build                 Build the binary into $(BIN_DIR)"
	@echo "  make run                   Run the already-built binary"
	@echo "  make start                 Build then run the binary"
	@echo "  make access-urls           Show URLs (ACCESS_PORT=$(ACCESS_PORT), must match app port)"
	@echo ""
	@echo "Container targets:"
	@echo "  make docker-build          Build IMAGE (default: intel/stream-manager:latest)"
	@echo "  make docker-run            Run IMAGE (local or pulled); ephemeral host port; see CONFIG_FILE, DATA_VOLUME, DATA_DIR"
	@echo "  make docker-stop           Stop and remove the running container (CONTAINER_NAME)"
	@echo ""
	@echo "  make clean                 Remove local build artifacts"

build: ## Build the binary on host into ./bin
	@mkdir -p $(BIN_DIR)
	CGO_ENABLED=0 GOOS=linux go build -buildmode=pie -ldflags "$(LDFLAGS)" -o $(BINARY_PATH) ./cmd/api-server
	@echo "Built $(BINARY_PATH) (version $(VERSION), build $(BUILD_NUMBER))"

run: ## Run the binary already built in ./bin
	@echo "Starting $(BINARY_PATH)"
	@PORT=$(ACCESS_PORT); \
	$(PRINT_ACCESS_URLS)
	$(BINARY_PATH)

start: build run ## Build then run the binary on host

access-urls: ## Show local and primary remote URLs for ACCESS_PORT
	@PORT=$(ACCESS_PORT); \
	$(PRINT_ACCESS_URLS)

docker-build: ## Build IMAGE (default: intel/stream-manager:latest).
	docker build \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_NUMBER=$(BUILD_NUMBER) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		-t $(IMAGE_REF) .
	@echo "Built image $(IMAGE_REF)"

docker-run: ## Run IMAGE (default: intel/stream-manager:latest); pull if missing.
ifneq ($(strip $(DATA_DIR)),)
	@echo "Preparing bind-mount directory $(DATA_DIR) for distroless uid/gid 65532"
	@mkdir -p $(DATA_DIR)
	@sudo chown -R 65532:65532 $(DATA_DIR)
	@sudo chmod 0700 $(DATA_DIR)
	$(eval STORAGE_MOUNT := -v $(DATA_DIR):/data)
else
	$(eval STORAGE_MOUNT := -v $(DATA_VOLUME):/data)
endif
ifneq ($(strip $(CONFIG_FILE)),)
	$(eval CONFIG_MOUNT := -v $(CONFIG_FILE):/config.json:ro)
endif
	docker run -d \
		--rm \
		--name $(CONTAINER_NAME) \
		--pull missing \
		-P \
		$(STORAGE_MOUNT) \
		$(CONFIG_MOUNT) \
		$(IMAGE_REF)
	@PORT=$$(docker port $(CONTAINER_NAME) $(CONTAINER_PORT)/tcp | head -1 | cut -d: -f2); \
	if [ -z "$$PORT" ]; then echo "Could not determine the published container port." >&2; exit 1; fi; \
	echo "Container '$(CONTAINER_NAME)' started."; \
	$(PRINT_ACCESS_URLS)

docker-stop: ## Stop and remove the running container
	docker stop $(CONTAINER_NAME)

clean: ## Remove built binaries from ./bin (keeps the directory)
	rm -f $(BIN_DIR)/*
