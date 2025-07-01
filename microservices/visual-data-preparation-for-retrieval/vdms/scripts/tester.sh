#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Test and generate coverage report for source code

# Run all tests in tests dir
test_dir=${PROJ_TEST_DIR:-./tests}
test_file=${test_dir}/${1}

FASTAPI_ENV=development poetry run coverage run --rcfile ./pyproject.toml -m pytest $test_file
FASTAPI_ENV=development poetry run coverage report -m --fail-under $COVERAGE_REQ