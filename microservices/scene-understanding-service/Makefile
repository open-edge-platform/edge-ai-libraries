# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Scene Understanding Service - convenience targets for build/run.
#
# RELEASE_TAG is the single source of truth for the image tag and is exported
# so docker compose picks it up for ${RELEASE_TAG} in docker-compose.yml.
# Override on the command line:  `make build RELEASE_TAG=dev`

RELEASE_TAG ?= 2026.2.0-rc1
REGISTRY    ?= intel

export RELEASE_TAG
export REGISTRY

.PHONY: help version build up down logs clean

help:
	@echo "Scene Understanding Service - available targets:"
	@echo "  make version   Print the release tag"
	@echo "  make build     Build the image tagged $(REGISTRY)/scene-understanding-service:$(RELEASE_TAG)"
	@echo "  make up        Start the service (docker compose up -d)"
	@echo "  make down      Stop the service"
	@echo "  make logs      Tail container logs"
	@echo "  make clean     Remove the built image and stopped containers"
	@echo ""
	@echo "Override the tag for a one-off build:  make build RELEASE_TAG=dev"

version:
	@echo $(RELEASE_TAG)

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f scene-understanding-service

clean:
	docker compose down --rmi local --remove-orphans
