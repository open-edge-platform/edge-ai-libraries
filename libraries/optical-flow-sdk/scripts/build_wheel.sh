#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Build a CPU-only self-contained wheel (static lib linked into _native).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv-wheel ]]; then
  python3 -m venv .venv-wheel
fi
# shellcheck disable=SC1091
source .venv-wheel/bin/activate
python -m pip install -U pip build scikit-build-core pybind11 numpy
python -m build --wheel --outdir dist/
ls -la dist/*.whl
echo "Install: .venv-wheel/bin/pip install dist/optical_flow_sdk-*.whl"
echo "Try:     .venv-wheel/bin/python python/samples/calc_flow_dis.py"
