#
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

IMAGE ?= dlsps2.0
COMPOSE_FILE ?= docker/docker-compose.yml
TEST_DEPS ?= pytest pytest-mock pytest-cov httpx2
# Checks that fire on C-extension and pydantic attributes (false positives)
PYLINT_DISABLE ?= no-member,unsubscriptable-object,no-name-in-module

RUN_IN_IMAGE = docker run --rm --user root --entrypoint /bin/bash \
	-v "$(CURDIR)/src:/home/pipeline-server/src:ro" \
	-v "$(CURDIR)/tests:/home/pipeline-server/tests:ro" \
	$(IMAGE) -c

.PHONY: all build lint test coverage help

all: build lint test

build:
	@# Help: Builds the dlsps2 image via docker compose
	docker compose -f $(COMPOSE_FILE) build dlstreamer-pipeline-server

lint:
	@# Help: Runs pylint (errors only) on src and tests inside the image
	$(RUN_IN_IMAGE) 'pip3 install -q pylint $(TEST_DEPS) >/dev/null 2>&1 && cd /home/pipeline-server && python3 -m pylint --errors-only --disable=$(PYLINT_DISABLE) src tests'

test:
	@# Help: Runs the pytest suite inside the image
	$(RUN_IN_IMAGE) 'pip3 install -q $(TEST_DEPS) >/dev/null 2>&1 && cd /home/pipeline-server && python3 -m pytest tests -q -p no:cacheprovider --tb=short'

coverage:
	@# Help: Runs the pytest suite with coverage for src
	$(RUN_IN_IMAGE) 'pip3 install -q $(TEST_DEPS) >/dev/null 2>&1 && cd /home/pipeline-server && python3 -m pytest tests -q -p no:cacheprovider --cov=src --cov-report=term-missing'

help:
	@# Help: Displays make targets
	@printf "%-20s %s\n" "Target" "Description"
	@printf "%-20s %s\n" "------" "-----------"
	@awk '/^[a-z]+:/{t=$$1; sub(":","",t)} /^\t@# Help:/{sub(/.*# Help: /,""); printf "%-20s %s\n", t, $$0}' Makefile
