<!--
Copyright (C) 2025 Intel Corporation

SPDX-License-Identifier: Apache-2.0
-->

# GPU ORB Extractor Feature Overview

This repository provides tutorials and usage guides for the GPU ORB Extractor
Feature, supporting both OpenCV-based and OpenCV-free workflows. The GPU ORB
Extractor library enables fast, thread-safe `keypoint` extraction for
visual SLAM and computer vision applications, with support for multiple
cameras and multi-threaded processing.

## Features

- High-performance GPU-accelerated ORB keypoint extraction
- Supports both OpenCV (`cv::Mat`, `cv::KeyPoint`) and OpenCV-free data structures
- Thread-safe API for multi-camera and multi-threaded use cases
- Flexible configuration for single or multiple ORB extractor objects

## Get Started

### System Requirements

Prepare the target system following the [official documentation](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/gsg_robot/prepare-system.html).

**Intel oneAPI Requirements:**
- Intel oneAPI 2025.3 with SYCL compiler support
- Clean build environment essential for SYCL compilation
- Requires namespace-qualified SYCL device code

**Note:** Some tests require TigerLake or AlderLake CPUs for SYCL runtime library support.

### Build

To build debian packages, export `ROS_DISTRO` env variable to desired platform and run `make build` command. After build process successfully finishes, built packages will be available in the root directory. The following command is an example for `Jazzy` distribution.

```bash
ROS_DISTRO=jazzy make build
```

You can list all built packages:

```bash
$ ls | grep -i .deb
liborb-lze_2.3-2_amd64.deb
liborb-lze-dev_2.3-2_amd64.deb
orb-extractor-lze-test_2.3-2_amd64.deb
ros-jazzy-orb-extractor-build-deps_2.3-2_amd64.deb
```

`*build-deps*.deb` package is generated during build process and installation of such packages could be skipped on target platform. `orb-extractor-lze-test_*.deb` is an empty/disabled test package used only for build-time testing and normally does not need to be installed on the target system.

To clean all build artifacts:

```bash
make clean
```

### Test

To run tests execute the below command with target `ROS_DISTRO` (example for Jazzy):

```bash
ROS_DISTRO=jazzy make tests
```

**Note:** Be aware that some of the tests can only be executed on TigerLake and AlderLake CPUs, otherwise they will fail on missing SYCL runtime library.

### Development

There is a set of prepared Makefile targets to speed up the development.

In particular, use the following Makefile target to run code linters.

```bash
make lint
```

Alternatively, you can run linters individually.

```bash
make lint-bash
make lint-clang
make lint-githubactions
make lint-json
make lint-markdown
make lint-python
make lint-yaml
```

To run license compliance validation:

```bash
make license-check
```

To see a full list of available Makefile targets:

```bash
$ make help
Target               Description
------               -----------
build                Build code using colcon
clean                Clean build artifacts
license-check        Perform a REUSE license check using docker container https://hub.docker.com/r/fsfe/reuse
lint                 Run all sub-linters using super-linter (using linters defined for this repo only)
lint-all             Run super-linter over entire repository (auto-detects code to lint)
lint-bash            Run Bash linter using super-linter
lint-clang           Run clang linter using super-linter
lint-githubactions   Run Github Actions linter using super-linter
lint-json            Run JSON linter using super-linter
lint-markdown        Run Markdown linter using super-linter
lint-python          Run Python linter using super-linter
lint-yaml            Run YAML linter using super-linter
source-package       Create source package tarball
tests                Run tests inside Docker container. Be aware that some of the tests could be executed only on TigerLake and AlderLake CPUs, otherwise it will fail on missing SYCL runtime library.
```

## Usage

The GPU ORB Extractor library provides tutorials and usage guides supporting both OpenCV-based and OpenCV-free workflows.

For detailed usage instructions and pre-requisites, refer to the [ORB Extractor Overview](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/dev_guide/tutorials_amr/perception/orb-extractor/package-use.html).

## Documentation

- [API Usage](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/dev_guide/tutorials_amr/perception/orb-extractor/api-use.html)
- [OpenCV-free Usage](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/dev_guide/tutorials_amr/perception/orb-extractor/orbocvfree-use.html)
- [Limitations](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/dev_guide/tutorials_amr/perception/orb-extractor/limitation.html)
For more details, see the GPU ORB Extractor [index page](https://docs.openedgeplatform.intel.com/edge-ai-suites/robotics-ai-suite/main/robotics/dev_guide/tutorials_amr/perception/orb-extractor/index.html).
