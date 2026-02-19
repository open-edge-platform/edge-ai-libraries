# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.DEFAULT_GOAL := help
.PHONY: build tests clean lint-all lint-clang lint-python lint-yaml lint-githubactions lint-bash lint-markdown lint-json source-package help 

ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# Version info for packaging
COMMIT := $(shell git rev-parse --short HEAD)
DATE := $(shell git log -1 --format=%cd --date=format:"%Y%m%d")
VERSION := $(COMMIT)-$(DATE)

ROS_DISTRO ?= humble
ifeq ($(ROS_DISTRO),humble)
	UBUNTU_CODENAME := jammy
else
	UBUNTU_CODENAME := noble
endif

build:
	@# Help: Build code using colcon with complete oneAPI 2025.3 clean build environment
	docker run --rm -t --platform linux/amd64 \
		-v $(ROOT_DIR):/src \
		-e DEBIAN_FRONTEND=noninteractive \
		-e ROS_DISTRO=$(ROS_DISTRO) \
		-e http_proxy=${http_proxy} \
		-e https_proxy=${https_proxy} \
		-e no_proxy=${no_proxy} \
		--pull never \
		amd64/ros:${ROS_DISTRO}-ros-base \
		bash -c "curl https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | \
			gpg --yes --dearmor --output /usr/share/keyrings/oneapi-archive-keyring.gpg && \
			echo \"deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main\" > /etc/apt/sources.list.d/oneAPI.list && \
            if [ \"\$$ROS_DISTRO\" = \"humble\" ]; then \
                curl https://eci.intel.com/repos/gpg-keys/GPG-PUB-KEY-INTEL-ECI.gpg | gpg --yes --dearmor --output /usr/share/keyrings/eci-archive-keyring.gpg && \
                echo 'deb [signed-by=/usr/share/keyrings/eci-archive-keyring.gpg] https://eci.intel.com/repos/${UBUNTU_CODENAME} isar main' | tee /etc/apt/sources.list.d/eci.list > /dev/null && \
                echo 'deb-src [signed-by=/usr/share/keyrings/eci-archive-keyring.gpg] https://eci.intel.com/repos/${UBUNTU_CODENAME} isar main' | tee -a /etc/apt/sources.list.d/eci.list > /dev/null; \
            fi && \
			apt-get -qq update --allow-unauthenticated && \
        	apt-get install -y clang devscripts equivs && \
        	echo 'Cleaning all build artifacts for oneAPI 2025.3 compatibility...' && \
        	cd /src && \
        	rm -rf ./debian ./build ./build-orbtest ./build-* ./CMakeCache.txt ./CMakeFiles ./cmake_install.cmake ./*.cmake && \
        	find . -name 'CMakeCache.txt' -delete && \
        	find . -name 'CMakeFiles' -type d -exec rm -rf {} + 2>/dev/null || true && \
        	find . -name '*.cmake' \( -path '*/build' -o -path '*/build-*' \) -delete 2>/dev/null || true && \
        	cp -r ./${ROS_DISTRO}/debian ./debian && \
        	echo 'Installing build dependencies with clean environment...' && \
        	mk-build-deps -i --host-arch amd64 --build-arch amd64 \
        	  -t \"apt-get -y -q -o Debug::pkgProblemResolver=yes --no-install-recommends --allow-downgrades\" debian/control && \
        	echo 'Starting clean CMake build for oneAPI 2025.3 SYCL compatibility...' && \
        	export CMAKE_GENERATOR_PLATFORM='' && \
        	export CMAKE_BUILD_PARALLEL_LEVEL=1 && \
        	dpkg-buildpackage && \
			mv ../*.deb . && \
        	echo 'Successfully built packages with oneAPI 2025.3 fixes'"

tests:
	@# Help: Run comprehensive tests (both OpenCV-free and OpenCV modes) in containerized environment  
	@echo "=== Running Comprehensive Test Suite ==="
	@echo "Testing both OpenCV-free (packaged) and OpenCV (full) variants..."
	docker run --rm -t --platform linux/amd64 \
		-v $(ROOT_DIR):/src \
		-e DEBIAN_FRONTEND=noninteractive \
		-e ROS_DISTRO=$(ROS_DISTRO) \
		--privileged \
		--device /dev/dri:/dev/dri \
		-w /src \
		-e no_proxy=${no_proxy} \
		amd64/ros:${ROS_DISTRO}-ros-base \
		./scripts/test.sh

clean:
	@# Help: Clean build artifacts
	rm -rf build* debian/ ros-* *.deb tests/build*

license-check:
	@# Help: Perform a REUSE license check using docker container https://hub.docker.com/r/fsfe/reuse
	docker run --rm --volume ${ROOT_DIR}:/data fsfe/reuse:5.0.2 lint

lint:
	@# Help: Run all sub-linters using super-linter (using linters defined for this repo only)
	VALIDATE_GITHUB_ACTIONS=true \
	VALIDATE_YAML=true \
	VALIDATE_JSON=true \
	VALIDATE_PYTHON_PYLINT=true \
	VALIDATE_PYTHON_FLAKE8=true \
	VALIDATE_BASH=true \
	VALIDATE_MARKDOWN=true \
	VALIDATE_CLANG_FORMAT=true \
		make lint-all

lint-all:
	@# Help: Run super-linter over entire repository (auto-detects code to lint)
	docker run --rm --platform linux/amd64 \
		-e SHELL=/bin/bash \
		-e RUN_LOCAL=true \
		--env-file ".github/linters/super-linter.env" \
		$(if $(VALIDATE_GITHUB_ACTIONS),-e VALIDATE_GITHUB_ACTIONS=$(VALIDATE_GITHUB_ACTIONS)) \
		$(if $(VALIDATE_YAML),-e VALIDATE_YAML=$(VALIDATE_YAML)) \
		$(if $(VALIDATE_JSON),-e VALIDATE_JSON=$(VALIDATE_JSON)) \
		$(if $(VALIDATE_PYTHON_PYLINT),-e VALIDATE_PYTHON_PYLINT=$(VALIDATE_PYTHON_PYLINT)) \
		$(if $(VALIDATE_PYTHON_FLAKE8),-e VALIDATE_PYTHON_FLAKE8=$(VALIDATE_PYTHON_FLAKE8)) \
		$(if $(VALIDATE_BASH),-e VALIDATE_BASH=$(VALIDATE_BASH)) \
		$(if $(VALIDATE_MARKDOWN),-e VALIDATE_MARKDOWN=$(VALIDATE_MARKDOWN)) \
		$(if $(VALIDATE_CLANG_FORMAT),-e VALIDATE_CLANG_FORMAT=$(VALIDATE_CLANG_FORMAT)) \
		-v $(ROOT_DIR):/tmp/lint \
			ghcr.io/super-linter/super-linter:slim-v8.1.0

lint-clang:
	@# Help: Run clang linter using super-linter
	VALIDATE_CLANG_FORMAT=true make lint-all

lint-python:
	@# Help: Run Python linter using super-linter
	VALIDATE_PYTHON_PYLINT=true VALIDATE_PYTHON_FLAKE8=true make lint-all

lint-yaml:
	@# Help: Run YAML linter using super-linter
	VALIDATE_YAML=true make lint-all

lint-githubactions:
	@# Help: Run Github Actions linter using super-linter
	VALIDATE_GITHUB_ACTIONS=true make lint-all

lint-bash:
	@# Help: Run Bash linter using super-linter
	VALIDATE_BASH=true make lint-all

lint-markdown:
	@# Help: Run Markdown linter using super-linter
	VALIDATE_MARKDOWN=true make lint-all

lint-json:
	@# Help: Run JSON linter using super-linter
	VALIDATE_JSON=true make lint-all

source-package:
	@# Help: Create source package tarball
	git archive --format=zip -o orb-extractor-$(VERSION).zip HEAD \
		Makefile README.md README-external.md REUSE.toml \
		CMakeLists.txt orblzeConfig.cmake.in orblze.pc.in \
		.github/linters cmake images include LICENSES samples src tests \
		humble jazzy

help:
	@printf "%-20s %s\n" "Target" "Description"
	@printf "%-20s %s\n" "------" "-----------"
	@grep -E '^[a-zA-Z0-9_%-]+:|^[[:space:]]+@# Help:' Makefile | \
	awk '\
		/^[a-zA-Z0-9_%-]+:/ { \
			target = $$1; \
			sub(":", "", target); \
		} \
		/^[[:space:]]+@# Help:/ { \
			if (target != "") { \
				help_line = $$0; \
				sub("^[[:space:]]+@# Help: ", "", help_line); \
				printf "%-20s %s\n", target, help_line; \
				target = ""; \
			} \
		}' | sort -k1,1
