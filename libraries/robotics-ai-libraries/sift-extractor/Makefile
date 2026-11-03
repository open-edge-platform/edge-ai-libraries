# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

.DEFAULT_GOAL := help
.PHONY: build host-build clean help local-build local-tests

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
# Parent libraries/ tree so sibling ../../sift-extractor (core) is visible in docker.
LIBRARIES_DIR := $(shell dirname $(shell dirname $(ROOT_DIR)))
PKG_REL := robotics-ai-libraries/sift-extractor

ROS_DISTRO ?= humble
ifeq ($(ROS_DISTRO),humble)
	UBUNTU_CODENAME := jammy
else
	UBUNTU_CODENAME := noble
endif

build:
	@# Help: Build debs in ros:${ROS_DISTRO} with oneAPI 2025.3 (mounts libraries/)
	docker run --rm -t --platform linux/amd64 --network=host \
		-v $(LIBRARIES_DIR):/src \
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
			cd /src/$(PKG_REL) && \
			rm -rf ./debian ./build ./build-core ./build-* ./CMakeCache.txt ./CMakeFiles && \
			cp -r ./${ROS_DISTRO}/debian ./debian && \
			chmod +x debian/rules && \
			mk-build-deps -i --host-arch amd64 --build-arch amd64 \
			  -t \"apt-get -y -q -o Debug::pkgProblemResolver=yes --no-install-recommends --allow-downgrades\" debian/control && \
			export CMAKE_BUILD_PARALLEL_LEVEL=1 && \
			dpkg-buildpackage -us -uc -b && \
			mv ../libsift-lze*.deb ../sift-extractor-lze-test*.deb . 2>/dev/null || mv ../\*.deb . && \
			echo Built packages in /src/$(PKG_REL)"

host-build:
	@# Help: Host-side dpkg-buildpackage (no Docker). Needs icpx/oneAPI + cmake.
	rm -rf $(ROOT_DIR)/debian $(ROOT_DIR)/build $(ROOT_DIR)/build-core
	cp -a $(ROOT_DIR)/$(ROS_DISTRO)/debian $(ROOT_DIR)/debian
	chmod +x $(ROOT_DIR)/debian/rules
	cd $(ROOT_DIR) && \
	  . /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; \
	  DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -us -uc -b -d
	mv $(ROOT_DIR)/../libsift-lze*.deb $(ROOT_DIR)/../sift-extractor-lze-test*.deb \
	   $(ROOT_DIR)/../ros-*-sift-extractor_*.buildinfo $(ROOT_DIR)/../ros-*-sift-extractor_*.changes \
	   $(ROOT_DIR)/ 2>/dev/null || true
	@ls -la $(ROOT_DIR)/*.deb

local-build:
	@# Help: Configure/build against a CMAKE_PREFIX_PATH that has sift_extractor
	cmake -S $(ROOT_DIR) -B $(ROOT_DIR)/build \
		-DCMAKE_BUILD_TYPE=Release \
		-DENABLE_OPENCV=ON \
		$(CMAKE_ARGS)
	cmake --build $(ROOT_DIR)/build --parallel

local-tests:
	ctest --test-dir $(ROOT_DIR)/build --output-on-failure

clean:
	rm -rf $(ROOT_DIR)/build $(ROOT_DIR)/build-core $(ROOT_DIR)/debian $(ROOT_DIR)/*.deb

help:
	@grep -E '^[^#].*:|^# Help:' $(MAKEFILE_LIST) | sed 's/:.*//;s/# Help: /  /' | head -40

