#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Run kvweave unit tests inside the vllm-kvweave Docker container.
#
# The test files are copied into the container before running since the
# full repo is not mounted there — only /kvweave_quant_src (read-only) is
# available, to build the kvweave_quant extension. kvweave_serde is sourced
# from the patched LMCache tree, not built by this repo's setup.py.
#
# Usage:
#   bash tests/run_unit_tests.sh              # accuracy tests only (default)
#   bash tests/run_unit_tests.sh --perf       # include performance benchmarks
#   bash tests/run_unit_tests.sh -k codec     # run only matching tests
#   bash tests/run_unit_tests.sh -v           # verbose output
set -euo pipefail

CONTAINER="${KVWEAVE_CONTAINER:-vllm-kvweave}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Directory inside container for tests
CONTAINER_TEST_DIR="/tmp/kvweave_tests"

# Check container is running
if ! docker inspect --format='{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "ERROR: Container '$CONTAINER' is not running."
    echo "Start it first, e.g.:"
    echo "  integration/vllm/vllm-start.sh              # normal serving container"
    echo "  DEBUG=1 integration/vllm/vllm-start.sh       # interactive debug shell"
    exit 1
fi

# Copy test files and pyproject.toml into container
echo "=== Syncing test files to container ==="
docker exec "$CONTAINER" rm -rf "$CONTAINER_TEST_DIR"
docker exec "$CONTAINER" mkdir -p "$CONTAINER_TEST_DIR/tests"
docker exec "$CONTAINER" pip install pytest
docker cp "${REPO_ROOT}/tests/." "${CONTAINER}:${CONTAINER_TEST_DIR}/tests/"
docker cp "${REPO_ROOT}/pyproject.toml" "${CONTAINER}:${CONTAINER_TEST_DIR}/pyproject.toml"

# Parse arguments
PYTEST_ARGS=()
PYTEST_BASE_ARGS=(tests/)
RUN_PERF=false

for arg in "$@"; do
    case "$arg" in
        --perf)
            RUN_PERF=true
            ;;
        *)
            PYTEST_ARGS+=("$arg")
            ;;
    esac
done

if [ "$RUN_PERF" = true ]; then
    # Override addopts so perf-marked tests are included.
    PYTEST_BASE_ARGS+=("-m" "")
fi

echo "=== Running kvweave unit tests in container '$CONTAINER' ==="
echo "Command: cd ${CONTAINER_TEST_DIR} && python -m pytest ${PYTEST_BASE_ARGS[*]} ${PYTEST_ARGS[*]}"
echo ""

DOCKER_EXEC_ARGS=("$CONTAINER" bash -lc '
set -eo pipefail
if [ -f /opt/intel/oneapi/setvars.sh ]; then
    set +u
    source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1
    set -u
fi
cd "$1"
shift
python -m pytest "$@"
' _ "$CONTAINER_TEST_DIR" "${PYTEST_BASE_ARGS[@]}" "${PYTEST_ARGS[@]}")

docker exec "${DOCKER_EXEC_ARGS[@]}"
