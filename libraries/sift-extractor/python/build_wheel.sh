#!/usr/bin/env bash
# Build a thin binary wheel: CMake pybind extension + package metadata.
# Does not bundle Intel GPU drivers / oneAPI; those remain a host dependency.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SIFT_WHEEL_BUILD_DIR:-/tmp/sift-extractor-wheel-build}"
PREFIX="${SIFT_WHEEL_PREFIX:-/tmp/sift-extractor-wheel-prefix}"
DIST_DIR="${SIFT_WHEEL_DIST:-$PY_DIR/dist}"

if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
  # shellcheck disable=SC1091
  source /opt/intel/oneapi/setvars.sh >/tmp/sift-wheel-setvars.log 2>&1 || true
fi

CMAKE_CXX_COMPILER="${CMAKE_CXX_COMPILER:-icpx}"
OPENCL_INC="${SIFT_OPENCL_INCLUDE_DIR:-/opt/intel/oneapi/compiler/latest/include}"

cmake -S "$ROOT" -B "$BUILD_DIR" \
  -DCMAKE_CXX_COMPILER="$CMAKE_CXX_COMPILER" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON \
  -DSIFT_ENABLE_OPENCL=ON \
  -DSIFT_BUILD_TESTS=OFF \
  -DSIFT_BUILD_SAMPLES=OFF \
  -DSIFT_BUILD_PYTHON=ON \
  -DSIFT_OPENCL_INCLUDE_DIR="$OPENCL_INC" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX"

cmake --build "$BUILD_DIR" --target sift_extractor_py --parallel "$(nproc)"

so="$(find "$BUILD_DIR" -maxdepth 1 -name '_native*.so' | head -n1)"
if [[ -z "$so" ]]; then
  echo "error: _native*.so not found under $BUILD_DIR" >&2
  exit 1
fi

rm -f "$PY_DIR"/sift_extractor/_native*.so
cp -f "$so" "$PY_DIR/sift_extractor/"
echo "Staged $(basename "$so") into package"

rm -rf "$PY_DIR/build" "$PY_DIR"/*.egg-info "$DIST_DIR"
mkdir -p "$DIST_DIR"
# setup.py BinaryWheel forces a platform tag (cpXY-linux) for the packaged .so.
(cd "$PY_DIR" && python3 setup.py bdist_wheel --dist-dir "$DIST_DIR")

echo "Wheels:"
ls -la "$DIST_DIR"/*.whl
